# Copyright (c) 2022 Acaisoft
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os
import signal
import sys
import threading
import importlib
import datetime
import time

from dateutil import parser

from bolt_api_client import BoltAPIClient
from bolt_utils.bolt_exceptions import MonitoringError, MonitoringWaitingExpired
from bolt_utils.bolt_enums import Status
from bolt_utils.bolt_logger import setup_custom_logger
from bolt_utils.bolt_consts import EXIT_STATUS_SUCCESS, EXIT_STATUS_ERROR

# TODO: need to refactor function run_monitor for working without recursion
sys.setrecursionlimit(7000)

# envs
EXECUTION_ID = os.getenv('BOLT_EXECUTION_ID')
DURING_TEST_INTERVAL = os.getenv('DURING_TEST_INTERVAL')

monitoring_module = importlib.import_module('bolt_monitoring.monitoring')
monitoring_func = getattr(monitoring_module, 'monitoring')

logger = setup_custom_logger(__name__)
bolt_api_client = BoltAPIClient()

# True - is alive | False - is not alive | None - was not running
DURING_TEST_IS_ALIVE = None
FLOW_WAS_TERMINATED_OR_FAILED = False
DEADLINE_FOR_WAITING_LOAD_TESTS = 60 * 10  # 10 min
INTERVAL_FOR_WAITING_LOAD_TESTS = 5


def _signals_exit_handler(signo, stack_frame):
    logger.info(f'Received signal {signo} | {stack_frame}')
    if signo == signal.SIGTERM:
        execution_instance = bolt_api_client.get_execution_instance(EXECUTION_ID, 'monitoring')
        status = execution_instance['execution_instance'][0]['status']
        logger.info(f'Signal handler. Status of monitoring is {status}')
        # if monitoring did not finish successfully -> exit with error
        if status != Status.SUCCEEDED.value:
            global FLOW_WAS_TERMINATED_OR_FAILED
            FLOW_WAS_TERMINATED_OR_FAILED = True
            logger.info('Monitoring did not finish successfully. Exit with error (code 1)')
            bolt_api_client.terminate()
            sys.exit(EXIT_STATUS_ERROR)
    bolt_api_client.terminate()
    logger.info('Exit from monitoring with code 0')
    sys.exit(EXIT_STATUS_SUCCESS)


signal.signal(signal.SIGTERM, _signals_exit_handler)


def run_monitoring(has_load_tests: bool, deadline: int, interval: int, stop_during_test_func=None):
    """
    Execute monitoring function every X sec
    """
    try:
        if DURING_TEST_IS_ALIVE is False:
            raise Exception(f'During test is not alive. Exit from monitoring')
        elif FLOW_WAS_TERMINATED_OR_FAILED:
            raise Exception(f'Flow was terminated or failed. Exit from monitoring')
        else:
            json_data = monitoring_func()
            if json_data is not None:
                bolt_api_client.insert_execution_metrics_data({
                    'timestamp': datetime.datetime.now().isoformat(), 'data': json_data})
    except Exception as e:
        # try to stop during test
        if stop_during_test_func is not None:
            stop_during_test_func()
        raise MonitoringError(e)
    else:
        time.sleep(interval)
        if time.time() > deadline:
            # try to stop during test
            if stop_during_test_func is not None:
                stop_during_test_func()
            # set status SUCCEEDED for execution when monitoring working without load_tests
            execution_data = bolt_api_client.get_execution(EXECUTION_ID)
            if not has_load_tests and execution_data['execution'][0]['status'] not in (
                    Status.ERROR.value, Status.FAILED.value, Status.TERMINATED.value, Status.SUCCEEDED.value):
                bolt_api_client.update_execution(execution_id=EXECUTION_ID, data={'status': Status.SUCCEEDED.value})
            # set status SUCCEEDED for execution instance
            bolt_api_client.update_execution_instance(
                EXECUTION_ID, 'monitoring', {'status': Status.SUCCEEDED.value, 'updated_at': 'now()'})
            return  # exit from function (as success)
        else:
            run_monitoring(has_load_tests, deadline, interval, stop_during_test_func)


def run_during_test():
    """
    Execute during test function every X sec using threading (background)
    """
    during_test_func = getattr(monitoring_module, 'during_test', None)
    if during_test_func is not None and DURING_TEST_INTERVAL is not None:
        global DURING_TEST_IS_ALIVE
        DURING_TEST_IS_ALIVE = True
        logger.info(f'Correctly detected during test with interval {DURING_TEST_INTERVAL}')
        stop_func = threading.Event()

        def call():
            """
            Call `during_test_func` and catch exceptions if function will crash
            """
            try:
                during_test_func()
            except Exception as ex:
                global DURING_TEST_IS_ALIVE
                DURING_TEST_IS_ALIVE = False
                logger.exception(f'Caught unknown exception from during test | {ex}')

        def loop():
            """
            Need for executing `call` function every X times in threads (target function in Thread)
            """
            call()
            while not stop_func.wait(int(DURING_TEST_INTERVAL)):
                call()

        threading.Thread(target=loop).start()  # open thread for `during test` and start
        return stop_func.set
    else:
        return None


def waiting_start_load_tests():
    """
    Wait until load tests is started
    """
    logger.info('Start execution function `waiting_start_load_tests`')
    deadline_for_waiting = time.time() + DEADLINE_FOR_WAITING_LOAD_TESTS
    while deadline_for_waiting > time.time():
        # check execution status
        execution_data = bolt_api_client.get_execution(EXECUTION_ID)
        if execution_data['execution'][0]['status'] in (
                Status.FAILED.value, Status.ERROR.value, Status.TERMINATED.value):
            return False  # negative exit from function (load_tests/flow crashed)
        # check execution instance status
        execution_instance = bolt_api_client.get_execution_instance(EXECUTION_ID, 'load_tests')
        try:
            status = execution_instance['execution_instance'][0]['status']
        except LookupError:
            logger.info('Error during fetching status for execution instance')
            time.sleep(INTERVAL_FOR_WAITING_LOAD_TESTS)
        else:
            logger.info(f'Retrieve execution instance status {status} from execution {EXECUTION_ID}')
            if status == 'READY':
                return True  # positive exit from function (load_tests started)
            else:
                time.sleep(INTERVAL_FOR_WAITING_LOAD_TESTS)
                continue  # continue iteration for waiting load tests
    return False  # negative exit from function (load_tests not started)


def get_or_create_execution_instance():
    try:
        response = bolt_api_client.get_execution_instance(EXECUTION_ID, 'monitoring')
        execution_instance = response['execution_instance'][0]
        logger.info(f'Found execution instance for monitoring | {execution_instance}')
        return execution_instance
    except IndexError:
        response = bolt_api_client.insert_execution_instance({'status': 'READY', 'instance_type': 'monitoring'})
        logger.info('Created new execution instance for monitoring with status READY')
        return response['insert_execution_instance']['returning'][0]


def main(**kwargs):
    logger.info('Start executing monitoring/during_test')
    # extract kwargs
    has_load_tests = kwargs.get('has_load_tests')
    monitoring_arguments = kwargs.get('monitoring_arguments', {})
    # run monitor if arguments was sending correctly
    if 'monitoring_interval' in monitoring_arguments and 'monitoring_duration' in monitoring_arguments:
        logger.info(f'Correctly detected arguments for monitoring | {monitoring_arguments}')
        execution_instance = get_or_create_execution_instance()
        interval = int(monitoring_arguments['monitoring_interval'])
        start_timestamp = parser.parse(execution_instance['created_at']).timestamp()
        deadline = int(start_timestamp) + int(monitoring_arguments['monitoring_duration'])
        logger.info(f'Monitoring deadline {datetime.datetime.fromtimestamp(deadline)}')
        if not has_load_tests:
            bolt_api_client.update_execution(execution_id=EXECUTION_ID, data={'status': 'MONITORING'})
            stop_during_test_func = run_during_test()
            run_monitoring(has_load_tests, deadline, interval, stop_during_test_func)
        else:
            load_tests_started = waiting_start_load_tests()
            if load_tests_started:
                stop_during_test_func = run_during_test()
                run_monitoring(has_load_tests, deadline, interval, stop_during_test_func)
            else:
                logger.info('Load test didnt start. The monitoring did not run')
                raise MonitoringWaitingExpired(f'Load tests didnt start {kwargs}')
    else:
        logger.info(f'Error during extracting arguments for monitoring | {monitoring_arguments}')
