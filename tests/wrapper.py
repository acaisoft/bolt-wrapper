"""
We have to wrap all imports for make sure
that locustfile.py does not overwrite original imports from this file during test execution.
For all imports we adding `wrap_` prefix.
"""
import os as wrap_os
import time as wrap_time
import csv as wrap_csv
import datetime as wrap_datetime
import locust.stats as wrap_locust_stats
import gql as wrap_gql

from locust import events as wrap_events
from transport import WrappedTransport

from logger import setup_custom_logger

# Envs
SENDING_INTERVAL_IN_SECONDS = int(wrap_os.getenv('SENDING_INTERVAL_IN_SECONDS', '2'))
GRAPHQL_URL = wrap_os.getenv('GRAPHQL_URL')
EXECUTION_ID = wrap_os.getenv('EXECUTION_ID')
HASURA_TOKEN = wrap_os.getenv('HASURA_TOKEN')
LOCUSTFILE_NAME = wrap_os.getenv('LOCUSTFILE_NAME')

wrap_locust_stats.CSV_STATS_INTERVAL_SEC = SENDING_INTERVAL_IN_SECONDS
wrap_logger = setup_custom_logger(__name__)

wrap_logger.info(f'wrap graphql: {GRAPHQL_URL}')
wrap_logger.info(f'wrap execution id: {EXECUTION_ID}')
wrap_logger.info(f'wrap token: {HASURA_TOKEN}')

# dynamically import source code from locustfile with tests
exec(f'from {LOCUSTFILE_NAME} import *')


class BoltAPIClient(object):
    """
    GraphQL client for communication with Bolt API (hasura)
    """

    def __init__(self):
        self.gql_client = wrap_gql.Client(
            retries=0,
            transport=WrappedTransport(
                url=GRAPHQL_URL,
                use_json=True,
                headers={'Authorization': f'Bearer {HASURA_TOKEN}'},
            )
        )

    def insert_aggregated_results(self, stats):
        query = wrap_gql.gql('''
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
        start = wrap_time.time()
        result = self.gql_client.execute(query, variable_values=stats)
        wrap_logger.info(f'Query `insert_aggregated_results` took {wrap_time.time() - start} seconds. Data {stats}')
        return result

    def insert_distribution_results(self, test_report):
        query = wrap_gql.gql('''
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
        start = wrap_time.time()
        result = self.gql_client.execute(query, variable_values=test_report)
        wrap_logger.info(
            f'Query `insert_distribution_results` took {wrap_time.time() - start} seconds. Data {test_report}')
        return result

    def update_execution(self, data):
        query = wrap_gql.gql('''
            mutation ($execution_id: uuid, $data: execution_set_input) {
                update_execution(where: {id: {_eq: $execution_id}}, _set: $data) {
                    affected_rows
                }
            }
        ''')
        start = wrap_time.time()
        variable_values = {'execution_id': EXECUTION_ID, 'data': data}
        wrap_logger.info(f'Query `update_execution` took {wrap_time.time() - start} seconds. Data {variable_values}')
        result = self.gql_client.execute(query, variable_values=variable_values)
        return result

    def insert_error_results(self, errors):
        query = wrap_gql.gql('''
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
        start = wrap_time.time()
        result = self.gql_client.execute(query, variable_values=errors)
        wrap_logger.info(f'Query `insert_error_results` took {wrap_time.time() - start} seconds. Data {errors}')
        return result


class LocustWrapper(object):
    """
    Wrapper class with help methods for sending and aggregating test results
    """
    dataset = []
    errors = {}
    stats = []
    stats_queue = []
    start_execution: wrap_datetime.datetime = None
    end_execution: wrap_datetime.datetime = None

    def __init__(self):
        self.bolt_api_client = BoltAPIClient()
        self.execution = EXECUTION_ID

    def prepare_stats_by_interval(self, data):
        """
        Preparing stats data by interval for sending to database
        :return stats: Dict:
            - execution_id: uuid
            - timestamp:  str:datetime-isoformat
            - number_of_successes: int
            - number_of_fails: int
            - number_of_errors: int
            - average_response_time: float
            - average_response_size: float
        """
        stats = {}
        timestamp = list(data.keys())[0]
        elements = data[timestamp]
        if not elements:
            return None
        # prepare dict for stats
        stats['execution_id'] = self.execution
        stats['timestamp'] = wrap_datetime.datetime.utcfromtimestamp(timestamp).isoformat()
        stats['number_of_successes'] = len([el for el in elements if el['event_type'] == 'success'])
        stats['number_of_fails'] = len([el for el in elements if el['event_type'] == 'failure'])
        stats['number_of_errors'] = len(set([el['exception'] for el in elements if bool(el['exception'])]))
        average_response_time = sum([el['response_time'] for el in elements]) / float(len(elements))
        stats['average_response_time'] = round(average_response_time, 2)
        average_response_size = sum([el['response_length'] for el in elements]) / float(len(elements))
        stats['average_response_size'] = round(average_response_size, 2)
        self.stats.append(stats)
        return stats

    def save_stats(self, send_all=False):
        # will be executed on the end test runner for sending all available data to database
        if send_all:
            for element in self.dataset:
                stats = self.prepare_stats_by_interval(element)
                if stats is not None:
                    database_save_event.fire(stats=stats)
            # send stats from queue if we lost connection during sending stats to database
            for stats in self.stats_queue:
                database_save_event.fire(stats=stats)
        # send first element from list to database if length of list more than 2
        elif len(self.dataset) > 2:
            first_element = self.dataset.pop(0)
            stats = self.prepare_stats_by_interval(first_element)
            # add stats to queue for sending
            self.stats_queue.append(stats)
            if stats is not None:
                database_save_event.fire(stats=stats)

    def push_event(self, data, event_type):
        # push failure event to dict with errors
        if event_type == 'failure':
            combined_key = '{0}/{1}/{2}'.format(data['request_type'], data['endpoint'], data['exception'])
            try:
                error = self.errors[combined_key]
                number_of_occurrences = error['number_of_occurrences']
                error['number_of_occurrences'] = number_of_occurrences + 1
            except KeyError:
                new_error = {combined_key: {
                    'execution_id': self.execution,
                    'number_of_occurrences': 1,
                    'name': data['endpoint'],
                    'error_type': data['request_type'],
                    'exception_data': data['exception']
                }}
                self.errors.update(new_error)
        # handle common type of errors
        last_timestamp = list(self.dataset[-1].keys())[0]
        now_timestamp = wrap_time.time()
        if int(now_timestamp) - int(last_timestamp) < SENDING_INTERVAL_IN_SECONDS:
            self.dataset[-1][last_timestamp].append(data)
        else:
            self.dataset.append({now_timestamp: [data]})
        # try to save/send stats for interval
        self.save_stats()


locust_wrapper = LocustWrapper()


def save_to_database(stats):
    """
    EventHook for sending aggregated results to database
    """
    locust_wrapper.bolt_api_client.insert_aggregated_results(stats)
    try:
        locust_wrapper.stats_queue.remove(stats)
    except ValueError:
        wrap_logger.info(f'Stats {stats} does not exist in queue {locust_wrapper.stats_queue}')


database_save_event = wrap_events.EventHook()
database_save_event += save_to_database


def success_handler(request_type, name, response_time, response_length):
    """
    Handler for catching successfully requests
    """
    received_data = {
        'execution_id': locust_wrapper.execution, 'endpoint': name, 'exception': '', 'request_type': request_type,
        'response_length': response_length, 'response_time': float(response_time), 'event_type': 'success',
        'timestamp': int(wrap_time.time()),
    }
    locust_wrapper.push_event(received_data, event_type='success')


def failure_handler(request_type, name, response_time, exception):
    """
    Handler for catching un-successfully requests
    """
    received_data = {
        'execution_id': locust_wrapper.execution, 'endpoint': name, 'exception': str(exception),
        'request_type': request_type, 'response_length': 0, 'response_time': float(response_time),
        'event_type': 'failure', 'timestamp': int(wrap_time.time()),
    }
    locust_wrapper.push_event(received_data, event_type='failure')


def quitting_handler():
    """
    Will be called before exiting test runner
    """
    # save remaining data from 'dataset' list
    locust_wrapper.save_stats(send_all=True)
    sum_success = sum([s['number_of_successes'] for s in locust_wrapper.stats])
    wrap_logger.info(f'Successfully requests: {sum_success}')
    wrap_logger.info(f'Stats: {locust_wrapper.stats}')
    wrap_logger.info(f'Errors: {locust_wrapper.errors}')
    wrap_logger.info(f'Start: {locust_wrapper.start_execution}. End: {locust_wrapper.end_execution}')
    # wait for updating data
    wrap_time.sleep(SENDING_INTERVAL_IN_SECONDS)

    # open report with requests and save to variable
    with open('test_report_requests.csv') as f:
        reader = wrap_csv.DictReader(f)
        requests_result = list(reader)

    # open report with distributions and save to variable
    with open('test_report_distribution.csv') as f:
        reader = wrap_csv.DictReader(f)
        distribution_result = list(reader)

    test_report = {
        'start': locust_wrapper.start_execution.isoformat(),
        'end': locust_wrapper.end_execution.isoformat(),
        'execution_id': locust_wrapper.execution,
        'request_result': requests_result,
        'distribution_result': distribution_result
    }
    locust_wrapper.bolt_api_client.insert_distribution_results(test_report)
    # prepare and send error results to database
    for error_item in list(locust_wrapper.errors.items()):
        _, value = error_item
        locust_wrapper.bolt_api_client.insert_error_results(value)


def start_handler():
    """
    Will be called before starting test runner
    """
    wrap_logger.info(f'Started locust tests with execution {EXECUTION_ID}')
    locust_wrapper.start_execution = wrap_datetime.datetime.now() - wrap_datetime.timedelta(seconds=2)
    # insert empty record to stats
    locust_wrapper.bolt_api_client.insert_aggregated_results({
        'execution_id': locust_wrapper.execution, 'timestamp': locust_wrapper.start_execution.isoformat(),
        'number_of_successes': 0, 'number_of_fails': 0, 'number_of_errors': 0,
        'average_response_time': 0, 'average_response_size': 0
    })
    locust_wrapper.bolt_api_client.update_execution({
        'status': 'RUNNING', 'start_locust': locust_wrapper.start_execution.isoformat()})
    if not locust_wrapper.dataset:
        locust_wrapper.dataset.append({wrap_datetime.datetime.now().timestamp(): []})


def stop_handler():
    """
    Will be called after finishing test runner
    """
    wrap_logger.info(f'Finished locust tests with execution {EXECUTION_ID}')
    locust_wrapper.end_execution = wrap_datetime.datetime.now()
    locust_wrapper.bolt_api_client.update_execution(
        {'status': 'FINISHED', 'end_locust': locust_wrapper.end_execution.isoformat()})


wrap_events.locust_start_hatching += start_handler
wrap_events.locust_stop_hatching += stop_handler
wrap_events.request_success += success_handler
wrap_events.request_failure += failure_handler
wrap_events.quitting += quitting_handler
