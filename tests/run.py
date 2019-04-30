import json
import sys
import os

from locust.main import main

from logger import setup_custom_logger
from api_client import BoltAPIClient

# TODO: temporary solution for disabling warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# envs
GRAPHQL_URL = os.getenv('BOLT_GRAPHQL_URL')
HASURA_TOKEN = os.getenv('BOLT_HASURA_TOKEN')
EXECUTION_ID = os.getenv('BOLT_EXECUTION_ID')
WORKER_TYPE = os.getenv('BOLT_WORKER_TYPE')
MASTER_HOST = os.getenv('BOLT_MASTER_HOST')

# logger
logger = setup_custom_logger(__name__)
logger.info('run v0.1.15')
logger.info(f'run graphql: {GRAPHQL_URL}')
logger.info(f'run execution id: {EXECUTION_ID}')
logger.info(f'run token: {HASURA_TOKEN}')
logger.info(f'worker type: {WORKER_TYPE}')
logger.info(f'master host: {MASTER_HOST}')


def _exit_with_status(status):
    logger.info(f'Exit with status {status}. For execution_id {EXECUTION_ID}')
    sys.exit(status)


class LocustRunner(object):
    def __init__(self):
        self.bolt_api_client = BoltAPIClient()

    def set_environments_for_tests(self, data):
        try:
            configuration = data['execution'][0]['configuration']
        except LookupError as ex:
            logger.info(f'Error during extracting test relations from database {ex}')
            _exit_with_status(1)
        else:
            if configuration['test_source']['source_type'] not in ('repository', 'test_creator'):
                logger.info('Invalid source_type value.')
                _exit_with_status(1)
            for envs in configuration.get('configuration_envvars', []):
                logger.info(f'run env "{envs["name"]}" == "{envs["value"]}"')
                os.environ[f'{envs["name"]}'] = envs['value']
            if configuration['test_source']['source_type'] == 'repository':
                os.environ['BOLT_LOCUSTFILE_NAME'] = 'locustfile'
                os.environ['BOLT_MIN_WAIT'] = '50'
                os.environ['BOLT_MAX_WAIT'] = '100'
            elif configuration['test_source']['source_type'] == 'test_creator':
                try:
                    test_creator = configuration['test_source']['test_creator']
                except LookupError as ex:
                    logger.info(f'Error during getting data for Test Creator {ex}')
                    _exit_with_status(1)
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
                        _exit_with_status(1)
                else:
                    logger.info(f'Cannot get data for test creator. Test creator data is {test_creator_data}')
                    _exit_with_status(1)
            else:
                logger.info(f'Cannot find locustile name for execution {EXECUTION_ID}')
                _exit_with_status(1)

    def get_locust_arguments(self, data, extra_arguments):
        argv = sys.argv or []
        try:
            configurations = data['execution'][0]['configuration']['configuration_parameters']
            if not configurations:
                raise LookupError('No arguments for configurations')
        except LookupError as ex:
            logger.info(f'Error during extracting arguments from database {ex}')
            _exit_with_status(1)
        else:
            argv.extend(['-f', 'wrapper.py'])
            # get and put arguments from database
            for config in configurations:
                argv.extend([config['parameter']['param_name'], config['value']])
            argv.extend(['--no-web'])
            argv.extend(['--csv=test_report'])
            if extra_arguments is not None:
                argv.extend(extra_arguments)
            return argv

    def master_slave_detector(self):
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
        self.bolt_api_client.insert_execution_instance({
            'status': 'READY', 'instance_type': WORKER_TYPE, 'expect_slaves': expect_slaves})
        return ['--master', f'--expect-slaves={expect_slaves}']  # additional arguments for master

    def prepare_slave_arguments(self):
        logger.info(f'Start preparing arguments for slave.')
        self.bolt_api_client.insert_execution_instance({
            'host': MASTER_HOST, 'port': 5557, 'status': 'READY', 'instance_type': WORKER_TYPE})
        return ['--slave', f'--master-host={MASTER_HOST}']  # additional arguments for slave


if __name__ == '__main__':
    locust_runner = LocustRunner()
    execution_data = locust_runner.bolt_api_client.get_execution(execution_id=EXECUTION_ID)
    locust_runner.set_environments_for_tests(execution_data)
    # master/slave
    additional_arguments = None
    is_master, is_slave = locust_runner.master_slave_detector()
    if is_master:
        number_of_slaves = execution_data['execution'][0]['configuration']['instances']
        additional_arguments = locust_runner.prepare_master_arguments(number_of_slaves)
    elif is_slave:
        additional_arguments = locust_runner.prepare_slave_arguments()
    # set arguments to locust
    logger.info(f'Arguments (sys.argv) before {sys.argv}')
    sys.argv = locust_runner.get_locust_arguments(execution_data, additional_arguments)
    logger.info(f'Arguments (sys.argv) after {sys.argv}')
    # monkey patch for returning 0 (success) status code
    sys.exit = lambda status: None
    main()  # test runner
