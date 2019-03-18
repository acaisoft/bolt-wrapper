import sys
import os

from gql import gql, Client
from locust.main import main
from gql.transport.requests import RequestsHTTPTransport

from logger import setup_custom_logger

# Envs
GRAPHQL_URL = os.getenv('GRAPHQL_URL')
EXECUTION_ID = os.getenv('EXECUTION_ID')
HASURA_GRAPHQL_ACCESS_KEY = os.getenv('HASURA_GRAPHQL_ACCESS_KEY')

logger = setup_custom_logger(__name__)
gql_client = Client(
    retries=0,
    transport=RequestsHTTPTransport(
        url=GRAPHQL_URL,
        use_json=True,
        headers={'X-Hasura-Access-Key': HASURA_GRAPHQL_ACCESS_KEY},
    )
)


def _exit_with_status(status):
    logger.info(f'Exit with status {status}. For execution_id {EXECUTION_ID}')
    sys.exit(status)


def get_data_for_execution():
    query = gql('''
        query ($execution_id: uuid) {
            execution(where: {id: {_eq: $execution_id}}) {
                configuration {
                    repository_id
                    configurationParameters {
                        value
                        parameter {
                            name
                            param_name
                            param_type
                        }
                    }
                    test_creator_configuration_m2m(order_by: {created_at: desc_nulls_last}, limit: 1) {
                        testCreator {
                            created_at
                            data
                            max_wait
                            min_wait
                        }
                    }
                }
            }
        }
    ''')
    result = gql_client.execute(query, variable_values={'execution_id': EXECUTION_ID})
    logger.info(f'Result of query for getting execution data: {result}')
    return result


def set_environments_for_tests(data):
    try:
        repository_id = data['execution'][0]['configuration']['repository_id']
        test_creator = data['execution'][0]['configuration']['test_creator_configuration_m2m']
    except LookupError as ex:
        logger.info(f'Error during extracting test relations from database {ex}')
        _exit_with_status(1)
    else:
        if repository_id and test_creator:
            logger.info('Found defined Repository and Test Creator. Only one test source should be used.')
            _exit_with_status(1)
        elif repository_id:
            os.environ['LOCUSTFILE_NAME'] = 'locustfile'
        elif test_creator:
            try:
                test_creator = test_creator[0]['testCreator']
            except LookupError as ex:
                logger.info(f'Error during getting data for Test Creator {ex}')
                _exit_with_status(1)
            os.environ['LOCUSTFILE_NAME'] = 'locustfile_generic'
            os.environ['MIN_WAIT'] = str(test_creator['min_wait'])
            os.environ['MAX_WAIT'] = str(test_creator['max_wait'])
            test_creator_data = test_creator['data']
            if test_creator_data:
                os.environ['TEST_CREATOR_DATA'] = test_creator_data
            else:
                logger.info(f'Cannot get data for test creator. Test creator data is {test_creator_data}')
                _exit_with_status(1)
        else:
            logger.info(f'Cannot find locustile name for execution {EXECUTION_ID}')
            _exit_with_status(1)


def get_locust_arguments(data):
    argv = sys.argv or []
    try:
        configurations = data['execution'][0]['configuration']['configurationParameters']
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
        return argv


if __name__ == '__main__':
    execution_data = get_data_for_execution()
    set_environments_for_tests(execution_data)
    logger.info(f'Arguments (sys.argv) before {sys.argv}')
    sys.argv = get_locust_arguments(execution_data)
    logger.info(f'Arguments (sys.argv) after {sys.argv}')
    # monkey patch for returning 0 (success) status code
    sys.exit = lambda status: None
    main()  # test runner
