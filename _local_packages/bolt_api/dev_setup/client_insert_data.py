import datetime
import random

from bolt_api import client
from bolt_api.upstream.devclient import devclient


bolt_api_client = client.BoltAPIClient(gql_client=devclient())


if __name__ == "__main__":
    # insert new user
    user = bolt_api_client.insert_user({'email': f'test-{random.randint(1, 1000000)}@email.com', 'active': True})
    print(f'User result {user}')

    # insert new project
    project = bolt_api_client.insert_project({'name': 'project-name', 'contact': 'test@email.com'})
    print(f'Project result {project}')

    # insert new repository
    repository = bolt_api_client.insert_repository(
        {'name': 'repo 1', 'url': 'http://url.com/hello', 'username': 'root', 'password': 'root'})
    print(f'Repository result {repository}')

    # insert new configuration type
    configuration_type = bolt_api_client.insert_configuration_type(
        {'name': f'Dally-{random.randint(1, 1000000)}', 'description': 'description type'})
    print(f'Configuration type result {configuration_type}')

    # insert new configuration
    configuration = bolt_api_client.insert_configuration(
        {'name': 'conf-1', 'repository_id': repository, 'project_id': project, 'type_id': configuration_type})
    print(f'Configuration result {configuration}')

    # insert new execution
    execution = bolt_api_client.insert_execution({'configuration': configuration})
    print(f'Execution result {execution}')

    # insert new aggregated results
    aggregated_results = bolt_api_client.insert_aggregated_results({
        'execution_id': execution,
        'number_of_fails': 5,
        'number_of_successes': 10,
        'number_of_errors': 15,
        'average_response_time': 12.34,
        'average_response_size': 14,
        'timestamp': datetime.datetime.now()
    })
    print(f'Aggregated results {aggregated_results}')

    # insert new distribution results
    distribution_results = bolt_api_client.insert_distribution_results({
        'execution_id': execution,
        'start': datetime.datetime.now(),
        'end': datetime.datetime.now(),
        'request_result': {'hello': 'world'},
        'distribution_result': {'test': [1, 2, 3, 4]}
    })
    print(f'Distribution results {distribution_results}')

    # insert new error results
    error_results = bolt_api_client.insert_error_results({
        'execution_id': execution,
        'name': 'error name',
        'error_type': 'error type',
        'exception_data': '{}',
        'number_of_occurrences': 150
    })
    print(f'Error results {error_results}')
