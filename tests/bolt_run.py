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
from gevent import monkey
monkey.patch_all(ssl=False, socket=False)


def stub(*args, **kwargs):
    pass


monkey.patch_all = stub

import json
import sys
import os
import importlib
import time

import requests.exceptions
from locust.main import main as locust_main

from bolt_utils.bolt_exceptions import MonitoringError, MonitoringWaitingExpired
from bolt_utils.bolt_logger import setup_custom_logger
from bolt_api_client import BoltAPIClient
from bolt_supervisor import Supervisor
from bolt_utils.bolt_enums import Status
from bolt_utils.bolt_consts import EXIT_STATUS_SUCCESS, EXIT_STATUS_ERROR

# TODO: temporary solution for disabling warnings
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# envs
WRAPPER_VERSION = '0.2.99'
GRAPHQL_URL = os.getenv('BOLT_GRAPHQL_URL')
HASURA_TOKEN = os.getenv('BOLT_HASURA_TOKEN')
EXECUTION_ID = os.getenv('BOLT_EXECUTION_ID')
WORKER_TYPE = os.getenv('BOLT_WORKER_TYPE')
MASTER_HOST = os.getenv('BOLT_MASTER_HOST')
NFS_MOUNT = os.getenv('BOLT_NFS_MOUNT_1')

# logger
logger = setup_custom_logger(__name__)
logger.info(f'run v{WRAPPER_VERSION}')
logger.info(f'run graphql: {GRAPHQL_URL}')
logger.info(f'run execution id: {EXECUTION_ID}')
logger.info(f'run token: {HASURA_TOKEN}')
logger.info(f'worker type: {WORKER_TYPE}')
logger.info(f'master host: {MASTER_HOST}')
logger.info(f'nfs mount path: {NFS_MOUNT}')
logger.info(os.environ)

SCENARIO_TYPE: str
MAX_GQL_RETRY = 3
GQL_RETRY_TIMEOUT = 3

no_keep_alive = True if WORKER_TYPE == 'slave' else False
bolt_api_client = BoltAPIClient(no_keep_alive=no_keep_alive)

IGNORED_ARGS = [
    'load_tests_repository_branch',
    'load_tests_file_name',
    'load_tests_users_per_worker'
]


def _exit_with_status(status, reason=None):
    logger.info(f'Exit with status {status}. For execution_id {EXECUTION_ID}')
    if reason is not None:
        logger.info(f'Reason: {reason}')
    bolt_api_client.terminate()
    sys.exit(status)


def _import_and_run(module_name, func_name='main', **kwargs):
    try:
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
    except (ModuleNotFoundError, AttributeError) as ex:
        logger.exception(f'Import error | {ex}')
        _exit_with_status(EXIT_STATUS_ERROR)
    except Exception as ex:
        logger.exception(f'Unknown exception during importing module/function for execution | {ex}')
        _exit_with_status(EXIT_STATUS_ERROR)
    else:
        start_time = time.time()
        try:
            func(**kwargs)
        except MonitoringError as ex:
            logger.exception(f'Caught exception during execution monitoring | {ex}')
            _exit_with_status(EXIT_STATUS_ERROR)
        except MonitoringWaitingExpired as ex:
            logger.exception(f'Monitoring timed out while waiting for load tests | {ex}')
            _exit_with_status(EXIT_STATUS_ERROR)
        except Exception as ex:
            logger.exception(f'Caught unknown exception during execution | {ex}')
            _exit_with_status(EXIT_STATUS_ERROR)
        else:
            total_time = int(time.time() - start_time)
            logger.info(f'Successfully executed function {module_name}.{func_name}. Time execution {total_time} sec.')
            _exit_with_status(EXIT_STATUS_SUCCESS)


class Runner(object):
    @staticmethod
    def set_configuration_environments(data):
        try:
            configuration = data['execution'][0]['configuration']
        except LookupError as ex:
            logger.exception(f'Error while extracting environment from configuration | {ex}')
            _exit_with_status(EXIT_STATUS_ERROR)
        else:
            for envs in configuration.get('configuration_envvars', []):
                logger.info(f'run env "{envs["name"]}" == "{envs["value"]}"')
                os.environ[f'{envs["name"]}'] = envs['value']

    @staticmethod
    def set_environments_for_load_tests(data):
        try:
            configuration = data['execution'][0]['configuration']
        except LookupError as ex:
            logger.exception(f'Error while setting environment for load tests | {ex}')
            _exit_with_status(EXIT_STATUS_ERROR)
        else:
            if configuration['test_source']['source_type'] not in ('repository', 'test_creator'):
                logger.info('Invalid source_type value')
                _exit_with_status(EXIT_STATUS_ERROR)
            if configuration['test_source']['source_type'] == 'repository':
                try:
                    parameters = data['execution'][0]['configuration']['configuration_parameters']
                    if not parameters:
                        raise LookupError('No arguments for configurations')
                    for p in parameters:
                        if p['parameter_slug'] == 'load_tests_file_name':
                            os.environ['BOLT_LOCUSTFILE_NAME'] = p['value'].split('.')[0]
                except Exception as ex:
                    logger.exception(f'Error during extracting locustfile name from execution parameters {ex}')
                    _exit_with_status(EXIT_STATUS_ERROR)
            elif configuration['test_source']['source_type'] == 'test_creator':
                try:
                    test_creator = configuration['test_source']['test_creator']
                except LookupError as ex:
                    logger.exception(f'Error while getting data for Test Creator | {ex}')
                    _exit_with_status(EXIT_STATUS_ERROR)
                    return
                os.environ['BOLT_LOCUSTFILE_NAME'] = 'locustfile_generic'
                os.environ['BOLT_MIN_WAIT'] = str(test_creator['min_wait'])
                os.environ['BOLT_MAX_WAIT'] = str(test_creator['max_wait'])
                test_creator_data = test_creator['data']
                if test_creator_data:
                    if isinstance(test_creator_data, dict):
                        os.environ['BOLT_TEST_CREATOR_DATA'] = json.dumps(test_creator_data)
                    elif isinstance(test_creator_data, str):
                        os.environ['BOLT_TEST_CREATOR_DATA'] = test_creator_data
                    else:
                        logger.info(f'Unknown type of test_creator_data: {type(test_creator_data)}')
                        _exit_with_status(EXIT_STATUS_ERROR)
                else:
                    logger.info(f'Cannot get data for Test Creator. Test Creator data is {test_creator_data}')
                    _exit_with_status(EXIT_STATUS_ERROR)
            else:
                logger.info(f'Cannot find locustile name for execution {EXECUTION_ID}')
                _exit_with_status(EXIT_STATUS_ERROR)

    @staticmethod
    def has_load_tests(data):
        try:
            configuration = data['execution'][0]['configuration']
        except LookupError as ex:
            logger.exception(f'Error checking if configuration has load tests | {ex}')
            _exit_with_status(EXIT_STATUS_ERROR)
        else:
            return configuration['has_load_tests']

    @staticmethod
    def get_monitoring_arguments(data):
        try:
            parameters = data['execution'][0]['configuration']['configuration_parameters']
            if not parameters:
                raise LookupError('No arguments for configurations')
        except LookupError as ex:
            logger.exception(f'Error during extracting arguments for monitoring from database | {ex}')
            _exit_with_status(EXIT_STATUS_ERROR)
        else:
            arguments = {}
            for p in parameters:
                parameter_slug = p['parameter_slug']
                if parameter_slug.startswith('monitoring_'):
                    arguments[parameter_slug] = p['value']
            return arguments

    @staticmethod
    def get_load_tests_arguments(data, extra_arguments, is_master):
        argv = sys.argv or []
        # delete `load_tests` argument from list of argv's
        for e in data['execution'][0]['configuration']['configuration_parameters']:
            if e['parameter']['param_name'] == '-c':
                e['parameter']['param_name'] = '-u'
            if e['parameter_slug'] == 'load_tests_duration':
                os.environ['BOLT_TEST_DURATION'] = e['value']

        try:
            argv.remove('load_tests')
        except ValueError:
            pass
        # preparing arguments for locust
        try:
            parameters = data['execution'][0]['configuration']['configuration_parameters']
            if not parameters:
                raise LookupError('No arguments for configurations')
        except LookupError as ex:
            logger.exception(f'Error during extracting arguments for locust from database {ex}')
            _exit_with_status(EXIT_STATUS_ERROR)
        else:
            argv.extend(['-f', 'bolt_locust_wrapper.py'])
            # get and put locust arguments from database for master only
            if is_master:
                for p in parameters:
                    parameter_slug = p['parameter_slug']
                    if parameter_slug.startswith('load_tests_') and parameter_slug not in IGNORED_ARGS:
                        argv.extend([p['parameter']['param_name'], p['value']])
                argv.extend(['--headless'])
                argv.extend(['--csv=test_report'])
            if extra_arguments is not None:
                argv.extend(extra_arguments)
            return argv

    @staticmethod
    def scenario_detector():
        """
        :return: is_pre_start: bool | is_post_stop: bool | is_monitoring: bool | is_load_tests: bool
        """
        try:
            scenario = sys.argv[1]
        except IndexError:
            logger.exception(f'Scenario type not found. Args {sys.argv}')
            _exit_with_status(EXIT_STATUS_ERROR)
        else:
            logger.info(f'Trying to detect scenario from arguments {sys.argv}')
            if scenario in ('pre_start', 'post_stop', 'monitoring', 'load_tests'):
                logger.info(f'Detected scenario {scenario}')
                global SCENARIO_TYPE  # additional set scenario as global variable
                SCENARIO_TYPE = scenario
                return scenario
            else:
                logger.info('Unknown scenario ...')
                _exit_with_status(EXIT_STATUS_ERROR)

    @staticmethod
    def master_slave_detector():
        if WORKER_TYPE == 'master':
            logger.info(f'Master detected.')
            return True, False  # is master
        elif WORKER_TYPE == 'slave':
            logger.info(f'Slave detected.')
            return False, True  # is slave
        else:
            logger.info('Master/slave not found.')
            return False, False  # unknown

    @staticmethod
    def prepare_master_arguments(expect_slaves):
        logger.info(f'Start preparing arguments for master.')
        bolt_api_client.insert_execution_instance({
            'status': 'READY', 'instance_type': WORKER_TYPE, 'expect-workers': expect_slaves})
        return ['--master', f'--expect-workers={expect_slaves}']  # additional arguments for master

    @staticmethod
    def prepare_slave_arguments():
        logger.info(f'Start preparing arguments for slave.')
        return ['--worker', f'--master-host={MASTER_HOST}']  # additional arguments for slave

    @staticmethod
    def flow_was_terminated_or_failed(execution_data):
        logger.info('Checking if the flow was terminated')
        status = execution_data['execution'][0]['status']
        if status in (Status.TERMINATED.value, Status.FAILED.value, Status.ERROR.value):
            return True
        else:
            return False


def main():
    runner = Runner()
    supervisor = Supervisor()
    logger.info('ARGS')
    logger.info(sys.argv)
    scenario_type = runner.scenario_detector()
    execution_data = None
    retry_count = 0
    while execution_data is None and retry_count < MAX_GQL_RETRY:
        try:
            execution_data = bolt_api_client.get_execution(execution_id=EXECUTION_ID)
        except requests.HTTPError as ex:
            retry_count += 1
            time.sleep(GQL_RETRY_TIMEOUT)
    if not execution_data:
        logger.error(f'Not able to gather execution data due to HTTP Error {ex}')
        sys.exit(1)
    # if flow terminated we should exit from container as success (without retries)
    if runner.flow_was_terminated_or_failed(execution_data):
        _exit_with_status(status=EXIT_STATUS_SUCCESS, reason='Flow failed or has been terminated')
    runner.set_configuration_environments(execution_data)
    if scenario_type == 'pre_start':
        _import_and_run('bolt_flow.pre_start')
    elif scenario_type == 'post_stop':
        _import_and_run('bolt_flow.post_stop')
    elif scenario_type == 'monitoring':
        supervisor.run()
        monitoring_arguments = runner.get_monitoring_arguments(execution_data)
        has_load_tests = runner.has_load_tests(execution_data)
        _import_and_run(
            'bolt_monitoring_wrapper',
            has_load_tests=has_load_tests, monitoring_arguments=monitoring_arguments
        )
    elif scenario_type == 'load_tests':
        runner.set_environments_for_load_tests(execution_data)
        # master/slave
        additional_arguments = None
        is_master, is_slave = runner.master_slave_detector()
        if is_master:
            supervisor.run()
            number_of_slaves = execution_data['execution'][0]['configuration']['instances']
            additional_arguments = runner.prepare_master_arguments(number_of_slaves)
        elif is_slave:
            additional_arguments = runner.prepare_slave_arguments()
        # set arguments to locust
        logger.info(f'Configuration parameters for execution {EXECUTION_ID}:\n'
                    f'{execution_data["execution"][0]["configuration"]["configuration_parameters"]}')
        logger.info(f'Arguments (sys.argv) before {sys.argv}')
        sys.argv = runner.get_load_tests_arguments(execution_data, additional_arguments, is_master)
        logger.info(f'Arguments (sys.argv) after {sys.argv}')
        # monkey patch for returning 0 (success) status code
        sys.exit = lambda status: None
        locust_main()  # locust test runner


if __name__ == '__main__':
    main()
