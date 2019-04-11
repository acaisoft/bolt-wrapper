import os

from gql import gql, Client
from transport import WrappedTransport
from logger import setup_custom_logger, log_time_execution

# envs
GRAPHQL_URL = os.getenv('GRAPHQL_URL')
HASURA_TOKEN = os.getenv('HASURA_TOKEN')

logger = setup_custom_logger(__name__)


class BoltAPIClient(object):
    """
    GraphQL client for communication with Bolt API (hasura)
    """
    def __init__(self):
        self.gql_client = Client(
            retries=0,
            transport=WrappedTransport(
                url=GRAPHQL_URL,
                use_json=True,
                headers={'Authorization': f'Bearer {HASURA_TOKEN}'},
            )
        )

    @log_time_execution(logger)
    def get_execution(self, execution_id):
        query = gql('''
            query ($execution_id: uuid) {
                execution(where: {id: {_eq: $execution_id}}) {
                    configuration {
                        instances
                        configuration_parameters {
                            value
                            parameter {
                                name
                                param_name
                                param_type
                            }
                        }
                        test_source {
                            source_type
                            test_creator {
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
        result = self.gql_client.execute(query, variable_values={'execution_id': execution_id})
        return result

    @log_time_execution(logger)
    def update_execution(self, execution_id, data):
        query = gql('''
            mutation ($execution_id: uuid, $data: execution_set_input) {
                update_execution(where: {id: {_eq: $execution_id}}, _set: $data) {
                    affected_rows
                }
            }
        ''')
        variable_values = {'execution_id': execution_id, 'data': data}
        result = self.gql_client.execute(query, variable_values=variable_values)
        return result

    @log_time_execution(logger)
    def insert_aggregated_results(self, stats):
        query = gql('''
            mutation (
                $execution_id: uuid, 
                $timestamp: timestamptz, 
                $number_of_successes: Int, 
                $number_of_fails: Int, 
                $number_of_errors: Int, 
                $average_response_time: Float, 
                $average_response_size: Float){ 
                    insert_result_aggregate(objects: [{ 
                        timestamp: $timestamp, 
                        number_of_successes: $number_of_successes, 
                        number_of_fails: $number_of_fails, 
                        number_of_errors: $number_of_errors, 
                        average_response_time: $average_response_time, 
                        average_response_size: $average_response_size}]){
                affected_rows }}
        ''')
        result = self.gql_client.execute(query, variable_values=stats)
        return result

    @log_time_execution(logger)
    def insert_distribution_results(self, test_report):
        query = gql('''
            mutation (
                $execution_id: uuid, 
                $request_result: json, 
                $distribution_result: json, 
                $start: timestamptz, 
                $end: timestamptz){
                    insert_result_distribution (objects: [{
                        request_result: $request_result, 
                        distribution_result: $distribution_result, 
                        start: $start, 
                        end: $end}]){
                affected_rows }} 
        ''')
        result = self.gql_client.execute(query, variable_values=test_report)
        return result

    @log_time_execution(logger)
    def insert_error_results(self, errors):
        query = gql('''
            mutation (
                $execution_id: uuid, 
                $name: String, 
                $error_type: String, 
                $exception_data: String, 
                $number_of_occurrences: Int){
                    insert_result_error (objects: [{ 
                        name: $name, 
                        error_type: $error_type, 
                        exception_data: $exception_data, 
                        number_of_occurrences: $number_of_occurrences}]){
                affected_rows }}
        ''')
        result = self.gql_client.execute(query, variable_values=errors)
        return result

    @log_time_execution(logger)
    def get_execution_instance(self, _id):
        query = gql('''
            query ($id: uuid) {
                execution_instance (where: {id: {_eq: $id}}) {
                    id
                }
            }
        ''')
        result = self.gql_client.execute(query, variable_values={'id': _id})
        return result

    @log_time_execution(logger)
    def insert_execution_instance(self, data):
        query = gql('''
            mutation ($data: execution_instance_insert_input!) {
                insert_execution_instance (objects: [$data]) {
                    affected_rows
                }
            }
        ''')
        result = self.gql_client.execute(query, variable_values={'data': data})
        return result

    @log_time_execution(logger)
    def update_execution_instance(self, _id, data):
        query = gql('''
            mutation ($id: uuid, $data: execution_instance_set_input!) {
                update_execution_instance (where: {id: {_eq: $id}}, _set: $data) {
                    affected_rows
                }
            }
        ''')
        variable_values = {'id': _id, 'data': data}
        result = self.gql_client.execute(query, variable_values=variable_values)
        return result
