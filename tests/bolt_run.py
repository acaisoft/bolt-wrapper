import datetime
import json
import sys
import os
import importlib
import time

from locust.main import main as locust_main

from bolt_exceptions import MonitoringExit
from bolt_logger import setup_custom_logger
from bolt_api_client import BoltAPIClient

# TODO: temporary solution for disabling warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# envs
WRAPPER_VERSION = '0.2.28'
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

# consts
EXIT_STATUS_SUCCESS = 0
EXIT_STATUS_ERROR = 1
SCENARIO_TYPE: str

no_keep_alive = True if WORKER_TYPE == 'slave' else False
bolt_api_client = BoltAPIClient(no_keep_alive=no_keep_alive)


def _exit_with_status(status):
    logger.info(f'Exit with status {status}. For execution_id {EXECUTION_ID}')
    sys.exit(status)


def _stage_log(msg, level='info'):
    bolt_api_client.insert_execution_stage_log({
        'timestamp': datetime.datetime.now().isoformat(), 'stage': SCENARIO_TYPE, 'level': level, 'msg': msg})


def _import_and_run(scenario_type, module_name, func_name='main', **kwargs):
    _stage_log(f'Starting {scenario_type.replace("_", " ")}')
    try:
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
    except (ModuleNotFoundError, AttributeError) as ex:
        logger.exception(f'Import error | {ex}')
        _stage_log(f'Import error', level='error')
        _exit_with_status(EXIT_STATUS_ERROR)
    except Exception as ex:
        logger.exception(f'Unknown exception during importing module/function for execution | {ex}')
        _stage_log(f'Unknown error', level='error')
        _exit_with_status(EXIT_STATUS_ERROR)
    else:
        _stage_log(f'Running')
        start_time = time.time()
        try:
            func(**kwargs)
        except MonitoringExit as ex:
            logger.exception(f'Caught exception during execution monitoring | {ex}')
            _stage_log(f'Error during execution', level='error')
            _exit_with_status(EXIT_STATUS_ERROR)
        except Exception as ex:
            logger.exception(f'Caught unknown exception during execution | {ex}')
            _stage_log(f'Unknown error during execution', level='error')
            _exit_with_status(EXIT_STATUS_ERROR)
        else:
            total_time = int(time.time() - start_time)
            logger.info(f'Successfully executed function {module_name}.{func_name}. Time execution {total_time} sec.')
            _stage_log(f'{scenario_type.replace("_", " ").capitalize()} finished')
            _exit_with_status(EXIT_STATUS_SUCCESS)


class Runner(object):
    @staticmethod
    def set_configuration_environments(data):
        try:
            configuration = data['execution'][0]['configuration']
        except LookupError as ex:
            logger.exception(f'Error during extracting environments from configuration | {ex}')
            _stage_log('Could not extract environments for configuration', level='error')
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
            logger.exception(f'Error during setting environments for load tests | {ex}')
            _stage_log('Could not set environments for load tests', level='error')
            _exit_with_status(EXIT_STATUS_ERROR)
        else:
            if configuration['test_source']['source_type'] not in ('repository', 'test_creator'):
                logger.info('Invalid source_type value')
                _exit_with_status(EXIT_STATUS_ERROR)
            if configuration['test_source']['source_type'] == 'repository':
                os.environ['BOLT_LOCUSTFILE_NAME'] = 'load_tests'
            elif configuration['test_source']['source_type'] == 'test_creator':
                try:
                    test_creator = configuration['test_source']['test_creator']
                except LookupError as ex:
                    logger.exception(f'Error during getting data for Test Creator | {ex}')
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
                        logger.info(f'Found unknown type for test_creator_data: {type(test_creator_data)}')
                        _exit_with_status(EXIT_STATUS_ERROR)
                else:
                    logger.info(f'Cannot get data for test creator. Test creator data is {test_creator_data}')
                    _exit_with_status(EXIT_STATUS_ERROR)
            else:
                logger.info(f'Cannot find locustile name for execution {EXECUTION_ID}')
                _exit_with_status(EXIT_STATUS_ERROR)

    @staticmethod
    def has_load_tests(data):
        try:
            configuration = data['execution'][0]['configuration']
        except LookupError as ex:
            logger.exception(f'Error during checking that configuration has load tests | {ex}')
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
            _stage_log('Occurred error during getting arguments for monitoring', level='error')
            _exit_with_status(EXIT_STATUS_ERROR)
        else:
            arguments = {}
            for p in parameters:
                parameter_slug = p['parameter_slug']
                if parameter_slug.startswith('monitoring_'):
                    arguments[parameter_slug] = p['value']
            return arguments

    @staticmethod
    def get_load_tests_arguments(data, extra_arguments):
        argv = sys.argv or []
        # delete `load_tests` argument from list of argv's
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
            _stage_log('Occurred error during getting arguments for load tests', level='error')
            _exit_with_status(EXIT_STATUS_ERROR)
        else:
            argv.extend(['-f', 'bolt_locust_wrapper.py'])
            # get and put locust arguments from database
            for p in parameters:
                parameter_slug = p['parameter_slug']
                if parameter_slug.startswith('load_tests_'):
                    argv.extend([p['parameter']['param_name'], p['value']])
            argv.extend(['--no-web'])
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
            logger.exception(f'Scenario type does not found. Args {sys.argv}')
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
            logger.info('Master/slave does not found.')
            return False, False  # unknown

    def prepare_master_arguments(self, expect_slaves):
        logger.info(f'Start preparing arguments for master.')
        bolt_api_client.insert_execution_instance({
            'status': 'READY', 'instance_type': WORKER_TYPE, 'expect_slaves': expect_slaves})
        return ['--master', f'--expect-slaves={expect_slaves}']  # additional arguments for master

    def prepare_slave_arguments(self):
        logger.info(f'Start preparing arguments for slave.')
        bolt_api_client.insert_execution_instance({
            'host': MASTER_HOST, 'port': 5557, 'status': 'READY', 'instance_type': WORKER_TYPE})
        return ['--slave', f'--master-host={MASTER_HOST}']  # additional arguments for slave


def main():
    runner = Runner()
    scenario_type = runner.scenario_detector()
    _stage_log('Initialization')
    execution_data = bolt_api_client.get_execution(execution_id=EXECUTION_ID)
    runner.set_configuration_environments(execution_data)
    if scenario_type == 'pre_start':
        _import_and_run(scenario_type, 'bolt_flow.pre_start')
    elif scenario_type == 'post_stop':
        _import_and_run(scenario_type, 'bolt_flow.post_stop')
    elif scenario_type == 'monitoring':
        monitoring_arguments = runner.get_monitoring_arguments(execution_data)
        has_load_tests = runner.has_load_tests(execution_data)
        _import_and_run(
            scenario_type, 'bolt_monitoring_wrapper',
            has_load_tests=has_load_tests, monitoring_arguments=monitoring_arguments
        )
    elif scenario_type == 'load_tests':
        _stage_log('Starting load test')
        runner.set_environments_for_load_tests(execution_data)
        # master/slave
        additional_arguments = None
        is_master, is_slave = runner.master_slave_detector()
        if is_master:
            number_of_slaves = execution_data['execution'][0]['configuration']['instances']
            additional_arguments = runner.prepare_master_arguments(number_of_slaves)
        elif is_slave:
            additional_arguments = runner.prepare_slave_arguments()
        # set arguments to locust
        logger.info(f'Arguments (sys.argv) before {sys.argv}')
        sys.argv = runner.get_load_tests_arguments(execution_data, additional_arguments)
        logger.info(f'Arguments (sys.argv) after {sys.argv}')
        # monkey patch for returning 0 (success) status code
        sys.exit = lambda status: None
        _stage_log('Running')
        locust_main()  # locust test runner
        _stage_log('Load test finished')


if __name__ == '__main__':
    main()
