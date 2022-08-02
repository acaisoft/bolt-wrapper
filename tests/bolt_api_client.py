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

import csv
import os

from datetime import datetime
from gql import gql, Client

from bolt_transport import WrappedTransport
from bolt_logger import setup_custom_logger, log_time_execution

# TODO: temporary solution for disabling warnings
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# envs
GRAPHQL_URL = os.getenv('BOLT_GRAPHQL_URL')
HASURA_TOKEN = os.getenv('BOLT_HASURA_TOKEN')

logger = setup_custom_logger(__name__)


def identifier(parts: list):
    return str(abs(hash(' '.join(map(lambda x: x.strip(), parts)).lower())))


class BoltAPIClient(object):
    """
    GraphQL client for communication with Bolt API (hasura)
    """

    def __init__(self, no_keep_alive=False):
        self.gql_client = Client(
            transport=WrappedTransport(
                no_keep_alive=no_keep_alive,
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
                    status
                    start
                    configuration {
                        instances
                        has_pre_test
                        has_post_test
                        has_load_tests
                        has_monitoring
                        configuration_parameters {
                            value
                            parameter_slug
                            parameter {
                                name
                                param_name
                                param_type
                            }
                        }
                        configuration_envvars {
                            name
                            value
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
        result = self.gql_client.transport.execute(query, variable_values={'execution_id': execution_id})
        return result.formatted["data"]

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
        result = self.gql_client.transport.execute(query, variable_values=variable_values)
        return result

    @log_time_execution(logger)
    def insert_aggregated_results(self, stats):
        ts = datetime.now().isoformat()
        request_tick_stats = stats.pop("requests", {})
        stats['requests'] = []
        stats['distributions'] = []

        # open report with distributions and save to variable
        if os.path.exists('test_report_stats.csv'):
            with open('test_report_stats.csv') as f:
                for r in csv.DictReader(f):
                    if not r["Name"] == "Total" and r["Type"] != "":
                        req_id = identifier([r['Type'], r['Name']])
                        stats['distributions'].append({
                            'timestamp': ts,
                            'identifier': req_id,
                            'method': r['Type'],
                            'name': r['Name'],
                            'num_requests': r['Request Count'],
                            'p50': r['50%'],
                            'p66': r['66%'],
                            'p75': r['75%'],
                            'p80': r['80%'],
                            'p90': r['90%'],
                            'p95': r['95%'],
                            'p98': r['98%'],
                            'p99': r['99%'],
                            'p100': r['100%'],
                        })
        else:
            logger.warn('no stats file')

        median_response_time = stats.pop("median_response_time", 0)
        requests_per_second = stats.pop("requests_per_second", 0)

        for request in request_tick_stats:
            for endpoint in request["stats"]:
                req_id = identifier([endpoint['method'], endpoint['name']])  # TODO it should be the same as in distribution
                stats['requests'].append({
                    'timestamp': ts,
                    'identifier': req_id,
                    'method': endpoint['method'],
                    'name': endpoint['name'],
                    'num_requests': endpoint['num_requests'],
                    'num_failures': endpoint['num_failures'],
                    'median_response_time': median_response_time,
                    'average_response_time': stats['average_response_time'],
                    'min_response_time': endpoint['min_response_time'],
                    'max_response_time': endpoint['max_response_time'],
                    'average_content_size': stats['average_response_size'],
                    'requests_per_second': requests_per_second,
                    'requests_per_tick': endpoint['num_requests'],
                    'successes_per_tick': endpoint['num_requests'] - endpoint['num_failures'] - endpoint['num_none_requests'],
                })

        stats['errors'] = []
        for ed in stats.pop('error_details', {}).values():
            ed_id = identifier([ed['error_type'], ed['name']])
            stats['errors'].append({
                'timestamp': ts,
                'identifier': ed_id,
                'method': ed['error_type'],
                'name': ed['name'],
                'exception_data': ed['exception_data'],
                'number_of_occurrences': ed['number_of_occurrences'],
            })

        query = gql('''
            mutation (
                $requests:[execution_requests_insert_input!]!, 
                $distributions:[execution_distribution_insert_input!]!,
                $errors:[execution_errors_insert_input!]!,
                $timestamp: timestamptz, 
                $number_of_successes: Int, 
                $number_of_fails: Int, 
                $number_of_errors: Int,
                $number_of_users: Int, 
                $average_response_time: numeric, 
                $average_response_size: numeric
            ){ 
                insert_execution_requests(objects: $requests) { affected_rows }
                insert_execution_distribution(objects: $distributions) { affected_rows }
                insert_execution_errors(objects: $errors) { affected_rows }
                insert_result_aggregate(objects: [{ 
                    timestamp: $timestamp, 
                    number_of_successes: $number_of_successes, 
                    number_of_fails: $number_of_fails, 
                    number_of_errors: $number_of_errors, 
                    number_of_users: $number_of_users, 
                    average_response_time: $average_response_time, 
                    average_response_size: $average_response_size
                }]) { affected_rows }
            }
        ''')
        if 'execution_id' in stats:
            del stats['execution_id']
        result = self.gql_client.transport.execute(query, variable_values=stats)
        return result

    @log_time_execution(logger)
    def insert_distribution_results(self, test_report):
        query = gql('''
            mutation (
                $execution_id: uuid, 
                $request_result: json, 
                $distribution_result: json, 
                $start: timestamptz, 
                $end: timestamptz
            ) {
                insert_result_distribution (objects: [{
                    request_result: $request_result, 
                    distribution_result: $distribution_result, 
                    start: $start, 
                    end: $end
                }]){ affected_rows }
            } 
        ''')
        result = self.gql_client.transport.execute(query, variable_values=test_report)
        return result

    @log_time_execution(logger)
    def insert_error_results(self, errors):
        query = gql('''
            mutation (
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
        del errors["execution_id"]
        result = self.gql_client.transport.execute(query, variable_values=errors)
        return result

    @log_time_execution(logger)
    def get_execution_instance(self, execution_id, instance_type):
        query = gql('''
            query ($execution_id: uuid, $instance_type: String) {
                execution_instance(where: {execution_id: {_eq: $execution_id}, instance_type: {_eq: $instance_type}}) {
                    id
                    status
                    instance_type
                    created_at
                    updated_at
                    execution {
                        status
                    }
                }
            }
        ''')
        variable_values = {'execution_id': execution_id, 'instance_type': instance_type}
        result = self.gql_client.transport.execute(query, variable_values=variable_values)
        return result

    @log_time_execution(logger)
    def insert_execution_instance(self, data):
        query = gql('''
            mutation ($data: execution_instance_insert_input!) {
                insert_execution_instance (objects: [$data]) {
                    affected_rows
                    returning {
                        id
                        status
                        instance_type
                        created_at
                        updated_at
                        execution {
                            status
                        }
                    }
                }
            }
        ''')
        result = self.gql_client.transport.execute(query, variable_values={'data': data})
        return result

    @log_time_execution(logger)
    def update_execution_instance(self, execution_id, instance_type, data):
        query = gql('''
            mutation ($execution_id: uuid, $instance_type: String, $data: execution_instance_set_input!) {
                update_execution_instance(where: {execution_id: {_eq: $execution_id}, 
                                                  instance_type: {_eq: $instance_type}}, _set: $data) {
                    affected_rows
                }
            }
        ''')
        variable_values = {'execution_id': execution_id, 'instance_type': instance_type, 'data': data}
        result = self.gql_client.transport.execute(query, variable_values=variable_values)
        return result

    @log_time_execution(logger)
    def insert_execution_metrics_data(self, data):
        query = gql('''
            mutation ($data: execution_metrics_data_insert_input!) {
                insert_execution_metrics_data (objects: [$data]){
                    affected_rows
                }
            }
        ''')
        result = self.gql_client.transport.execute(query, variable_values={'data': data})
        return result

    @log_time_execution(logger)
    def insert_execution_stage_log(self, data):
        query = gql('''
            mutation ($data: execution_stage_log_insert_input!) {
                insert_execution_stage_log (objects: [$data]){
                    affected_rows
                }
            }
        ''')
        result = self.gql_client.transport.execute(query, variable_values={'data': data})
        return result

