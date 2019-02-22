import sys
import os

from gql import gql, Client
from locust.main import main
from gql.transport.requests import RequestsHTTPTransport

# ENVs
GRAPHQL_URL = os.getenv('GRAPHQL_URL')
EXECUTION_ID = os.getenv('EXECUTION_ID')
HASURA_GRAPHQL_ACCESS_KEY = os.getenv('HASURA_GRAPHQL_ACCESS_KEY')

gql_client = Client(
    retries=0,
    transport=RequestsHTTPTransport(
        url=GRAPHQL_URL,
        use_json=True,
        headers={'X-Hasura-Access-Key': HASURA_GRAPHQL_ACCESS_KEY},
    )
)


def get_locust_arguments_from_database():
    argv = sys.argv or []
    query = gql('''
        query ($execution_id: uuid) { 
            execution (where: {id: {_eq: $execution_id}}) {
                id
                configuration {
                    id
                    name
                    configurationParameters {
                        value
                        parameter {
                            name
                            param_name
                            param_type
                        }
                    }
                }
            }
        }
    ''')
    result = gql_client.execute(query, variable_values={'execution_id': EXECUTION_ID})
    print(f'Result of query: {result}')
    try:
        configurations = result['execution'][0]['configuration']['configurationParameters']
    except LookupError as ex:
        print(f'Error during extracting arguments from database {ex}')
        return argv
    else:
        argv.extend(['-f', 'wrapper.py'])
        # get and put arguments from database
        for config in configurations:
            argv.extend([config['parameter']['param_name'], config['value']])
        argv.extend(['--no-web'])
        argv.extend(['--csv=test_report'])
        return argv


if __name__ == '__main__':
    print(f'Arguments (sys.argv) before {sys.argv}')
    sys.argv = get_locust_arguments_from_database()
    print(f'Arguments (sys.argv) after {sys.argv}')
    sys.exit(main())  # test runner
