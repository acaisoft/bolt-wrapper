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

from locust import events as wrap_events, runners as wrap_runners

from logger import setup_custom_logger as wrap_setup_custom_logger
from api_client import BoltAPIClient as WrapBoltAPIClient

# TODO: temporary solution for disabling warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Envs
SENDING_INTERVAL_IN_SECONDS = int(wrap_os.getenv('SENDING_INTERVAL_IN_SECONDS', '2'))
GRAPHQL_URL = wrap_os.getenv('GRAPHQL_URL')
HASURA_TOKEN = wrap_os.getenv('HASURA_TOKEN')
EXECUTION_ID = wrap_os.getenv('EXECUTION_ID')
WORKER_TYPE = wrap_os.getenv('WORKER_TYPE')
LOCUSTFILE_NAME = wrap_os.getenv('LOCUSTFILE_NAME')

wrap_locust_stats.CSV_STATS_INTERVAL_SEC = SENDING_INTERVAL_IN_SECONDS
wrap_logger = wrap_setup_custom_logger(__name__)

# dynamically import source code from locustfile with tests
exec(f'from {LOCUSTFILE_NAME} import *')


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
    is_started = False
    is_finished = False

    def __init__(self):
        self.bolt_api_client = WrapBoltAPIClient()
        self.execution = EXECUTION_ID

    def prepare_stats_by_interval_common(self, data):
        """
        Preparing stats data by interval for sending to database for common cases
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
        stats['number_of_users'] = wrap_runners.locust_runner.user_count
        average_response_time = sum([el['response_time'] for el in elements]) / float(len(elements))
        stats['average_response_time'] = round(average_response_time, 2)
        average_response_size = sum([el['response_length'] for el in elements]) / float(len(elements))
        stats['average_response_size'] = round(average_response_size, 2)
        self.stats.append(stats)
        return stats

    def prepare_stats_by_interval_master(self, data):
        """
        Preparing stats data by interval for sending to database when WORKER_TYPE is 'master'
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
        errors = []
        number_of_requests = 0
        number_of_failures = 0
        total_response_time = 0
        total_content_length = 0
        for el in elements:
            number_of_requests += el['stats_total']['num_requests']
            number_of_failures += el['stats_total']['num_failures']
            total_response_time += el['stats_total']['total_response_time']
            total_content_length += el['stats_total']['total_content_length']
            if el['errors']:
                errors.extend(list(el['errors'].values()))
        stats['execution_id'] = self.execution
        stats['timestamp'] = wrap_datetime.datetime.utcfromtimestamp(timestamp).isoformat()
        stats['number_of_successes'] = number_of_requests - number_of_failures
        stats['number_of_fails'] = number_of_failures
        stats['number_of_users'] = wrap_runners.locust_runner.user_count
        number_of_errors = len(set(
            ['{1}/{1}/{2}'.format(error['method'], error['name'], error['error']) for error in errors]))
        stats['number_of_errors'] = number_of_errors
        try:
            stats['average_response_time'] = int(float(total_response_time) / number_of_requests)
        except (ZeroDivisionError, Exception) as ex:
            wrap_logger.info('Caught exception during calculating `average_response_time`')
            wrap_logger.info(f'{total_response_time} | {number_of_requests} | {ex}')
            stats['average_response_time'] = 0
        try:
            stats['average_response_size'] = int(float(total_content_length) / number_of_requests)
        except (ZeroDivisionError, Exception) as ex:
            wrap_logger.info('Caught exception during calculating `average_response_size`')
            wrap_logger.info(f'{total_content_length} | {number_of_requests} | {ex}')
            stats['average_response_size'] = 0
        self.stats.append(stats)
        return stats

    def save_stats(self, send_all=False):
        # will be executed on the end test runner for sending all available data to database
        if send_all:
            for element in self.dataset:
                if WORKER_TYPE == 'master':
                    stats = self.prepare_stats_by_interval_master(element)
                else:
                    stats = self.prepare_stats_by_interval_common(element)
                if stats is not None:
                    database_save_event.fire(stats=stats)
            # send stats from queue if we lost connection during sending stats to database
            for stats in self.stats_queue:
                database_save_event.fire(stats=stats)
        # send first element from list to database if length of list more than 2
        elif len(self.dataset) > 2:
            first_element = self.dataset.pop(0)
            if WORKER_TYPE == 'master':
                stats = self.prepare_stats_by_interval_master(first_element)
            else:
                stats = self.prepare_stats_by_interval_common(first_element)
            # add stats to queue for sending
            self.stats_queue.append(stats)
            if stats is not None:
                database_save_event.fire(stats=stats)

    def push_event(self, data, event_type):
        # extracting errors for common cases (when WORKER_TYPE is not 'master' or 'slave')
        if event_type == 'failure':
            combined_key = '{0}/{1}/{2}'.format(data['request_type'], data['endpoint'], data['exception'])
            try:
                error = self.errors[combined_key]
                error['number_of_occurrences'] = error['number_of_occurrences'] + 1
            except KeyError:
                new_error = {combined_key: {
                    'execution_id': self.execution, 'number_of_occurrences': 1, 'name': data['endpoint'],
                    'error_type': data['request_type'], 'exception_data': data['exception']
                }}
                self.errors.update(new_error)
        # extracting errors when WORKER_TYPE is 'master'
        elif event_type == 'master' and 'errors' in data.keys() and data['errors']:
            for error in data['errors'].values():
                combined_key = '{0}/{1}/{2}'.format(error['method'], error['name'], error['error'])
                try:
                    _error = self.errors[combined_key]
                    _error['number_of_occurrences'] += error['occurences']
                except KeyError:
                    new_error = {combined_key: {
                        'execution_id': self.execution, 'number_of_occurrences': error['occurences'],
                        'name': error['name'], 'error_type': error['method'], 'exception_data': error['error']
                    }}
                    self.errors.update(new_error)
        # push event to dataset for common cases
        last_timestamp = list(self.dataset[-1].keys())[0]
        now_timestamp = wrap_time.time()
        if int(now_timestamp) - int(last_timestamp) < SENDING_INTERVAL_IN_SECONDS:
            self.dataset[-1][last_timestamp].append(data)
        else:
            self.dataset.append({now_timestamp: [data]})
        # try to save/send stats for interval
        self.save_stats()


locust_wrapper = LocustWrapper()


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
    if not locust_wrapper.is_finished:
        locust_wrapper.end_execution = wrap_datetime.datetime.now()
        locust_wrapper.bolt_api_client.update_execution(
            execution_id=EXECUTION_ID,
            data={'status': 'FINISHED', 'end_locust': locust_wrapper.end_execution.isoformat()}
        )
        # save remaining data from 'dataset' list
        locust_wrapper.save_stats(send_all=True)
        sum_success = sum([s['number_of_successes'] for s in locust_wrapper.stats])
        wrap_logger.info(f'Sum success: {sum_success}. Stats {locust_wrapper.stats}. Errors {locust_wrapper.errors}')
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

        # remove Total from data (doesn't make sense in different columns)
        for index, v in enumerate(requests_result):
            if v.get('Name', None) == 'Total':
                requests_result.pop(index)
                break

        # split contents of distribution's Name into Method-Description
        for index, v in enumerate(distribution_result):
            dist_name = v.get('Name', None)
            if dist_name:
                parts = dist_name.split(' ', 1)
                if len(parts) > 1:
                    distribution_result[index]['Method'] = parts[0]
                    distribution_result[index]['Name'] = parts[1]

        locust_wrapper.bolt_api_client.insert_distribution_results({
            'start': locust_wrapper.start_execution.isoformat(),
            'end': locust_wrapper.end_execution.isoformat(),
            'execution_id': locust_wrapper.execution,
            'request_result': requests_result,
            'distribution_result': distribution_result
        })
        # prepare and send error results to database
        for error_item in list(locust_wrapper.errors.items()):
            _, value = error_item
            locust_wrapper.bolt_api_client.insert_error_results(value)
        locust_wrapper.is_finished = True


def start_handler():
    """
    Will be called before starting test runner
    """
    if not locust_wrapper.is_started:
        wrap_logger.info(f'Started locust tests with execution {EXECUTION_ID}')
        locust_wrapper.start_execution = wrap_datetime.datetime.now() - wrap_datetime.timedelta(
            seconds=SENDING_INTERVAL_IN_SECONDS)
        # insert empty record to stats
        locust_wrapper.bolt_api_client.insert_aggregated_results({
            'execution_id': locust_wrapper.execution, 'timestamp': locust_wrapper.start_execution.isoformat(),
            'number_of_successes': 0, 'number_of_fails': 0, 'number_of_errors': 0, 'number_of_users': 0,
            'average_response_time': 0, 'average_response_size': 0
        })
        locust_wrapper.bolt_api_client.update_execution(
            execution_id=EXECUTION_ID,
            data={'status': 'RUNNING', 'start_locust': locust_wrapper.start_execution.isoformat()})
        if not locust_wrapper.dataset:
            locust_wrapper.dataset.append({wrap_datetime.datetime.now().timestamp(): []})
        locust_wrapper.is_started = True


def report_from_slave_handler(client_id, data):
    """
    Using when WORKER_TYPE is 'master' for receiving stats from slaves.
    """
    if locust_wrapper.is_started:
        locust_wrapper.push_event(data=data, event_type=WORKER_TYPE)


def save_to_database(stats):
    """
    EventHook for sending aggregated results to database
    """
    # TODO: it is hotfix, need to find why we getting None item inside 'stats'
    if stats is not None and stats:
        locust_wrapper.bolt_api_client.insert_aggregated_results(stats)
    try:
        locust_wrapper.stats_queue.remove(stats)
    except ValueError:
        wrap_logger.info(f'Stats {stats} does not exist in queue {locust_wrapper.stats_queue}')


if WORKER_TYPE == 'master':
    database_save_event = wrap_events.EventHook()
    database_save_event += save_to_database
    wrap_events.slave_report += report_from_slave_handler  # catch stats from slaves
    wrap_events.master_start_hatching += start_handler  # start testing (master)
    wrap_events.quitting += quitting_handler  # stop testing (master)
elif WORKER_TYPE == 'slave':
    pass  # slave need just for sending stats to master
else:
    # handlers for common testing (without master/slave)
    database_save_event = wrap_events.EventHook()
    database_save_event += save_to_database
    wrap_events.locust_start_hatching += start_handler
    wrap_events.request_success += success_handler
    wrap_events.request_failure += failure_handler
    wrap_events.quitting += quitting_handler
