import os
import sys
import threading
import importlib
import datetime
import time

from dateutil import parser

from bolt_api_client import BoltAPIClient
from bolt_exceptions import MonitoringError, MonitoringWaitingExpired
from bolt_enums import Status
from bolt_logger import setup_custom_logger

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
DEADLINE_FOR_WAITING_LOAD_TESTS = 60 * 10  # 10 min
INTERVAL_FOR_WAITING_LOAD_TESTS = 5


def run_monitoring(has_load_tests: bool, deadline: int, interval: int, stop_during_test_func=None):
    """
    Execute monitoring function every X sec
    """
    try:
        if DURING_TEST_IS_ALIVE is False:
            raise Exception(f'During test is not alive. Exit from monitoring.')
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
            execution_data = bolt_api_client.get_execution(EXECUTION_ID)
            # set status FINISHED for execution when monitoring working without load_tests
            if not has_load_tests and execution_data['execution'][0]['status'] not in (
                    Status.ERROR.value, Status.FAILED.value, Status.TERMINATED.value, Status.SUCCEEDED.value):
                bolt_api_client.update_execution(execution_id=EXECUTION_ID, data={'status': Status.FINISHED.value})
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
