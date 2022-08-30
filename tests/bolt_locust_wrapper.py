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

"""
We have to wrap all imports to make sure that locustfile.py does not overwrite original imports from this file
during test execution. For all imports we add `wrap_` prefix.
"""
import os as wrap_os
import re as wrap_re
import time as wrap_time
import datetime as wrap_datetime

import locust.stats as wrap_locust_stats

from locust import events as wrap_events
from locust.runners import MasterRunner

from bolt_logger import setup_custom_logger as wrap_setup_custom_logger
from bolt_api_client import BoltAPIClient as WrapBoltAPIClient
import bolt_locust_wrapper_parser as parser

# TODO: temporary solution for disabling warnings
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Envs
SENDING_INTERVAL_IN_SECONDS = int(wrap_os.getenv('BOLT_SENDING_INTERVAL_IN_SECONDS', '1'))
GRAPHQL_URL = wrap_os.getenv('BOLT_GRAPHQL_URL')
HASURA_TOKEN = wrap_os.getenv('BOLT_HASURA_TOKEN')
EXECUTION_ID = wrap_os.getenv('BOLT_EXECUTION_ID')
WORKER_TYPE = wrap_os.getenv('BOLT_WORKER_TYPE')
LOCUSTFILE_NAME = wrap_os.getenv('BOLT_LOCUSTFILE_NAME')

wrap_locust_stats.CSV_STATS_INTERVAL_SEC = SENDING_INTERVAL_IN_SECONDS
wrap_logger = wrap_setup_custom_logger(__name__)
wrap_logger.propagate = False

# dynamically import source code from locustfile with tests
exec(f'from {LOCUSTFILE_NAME} import *')


class LocustWrapper(object):
    """
    Wrapper class with help methods for sending and aggregating test results
    """
    dataset = []
    dataset_timestamps = []
    errors = {}
    stats = []
    stats_queue = []
    users = []
    start_execution: wrap_datetime.datetime = None
    end_execution: wrap_datetime.datetime = None
    is_started = False
    is_finished = False
    environment = None

    def __init__(self):
        if WORKER_TYPE != 'slave':
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
            empty_stats = {
                'execution_id': locust_wrapper.execution,
                'timestamp': wrap_datetime.datetime.utcfromtimestamp(timestamp).isoformat(),
                'number_of_users': 0,
                'number_of_fails': 0,
                'number_of_successes': 0,
                'number_of_errors': 0,
                'average_response_time': 0,
                'average_response_size': 0
            }
            return empty_stats
        # prepare dict for stats
        stats['execution_id'] = self.execution
        stats['timestamp'] = wrap_datetime.datetime.utcfromtimestamp(timestamp).isoformat()
        stats['number_of_successes'] = len([el for el in elements if el['event_type'] == 'success'])
        stats['number_of_fails'] = len([el for el in elements if el['event_type'] == 'failure'])
        stats['number_of_errors'] = len(set([el['exception'] for el in elements if bool(el['exception'])]))
        number_of_users = self.environment.runner.user_count
        if number_of_users == 0 and len(self.users):
            number_of_users = int(sum(self.users) / len(self.users) * 0.60)
        stats['number_of_users'] = number_of_users
        average_response_time = sum([el['response_time'] for el in elements]) / float(len(elements))
        stats['average_response_time'] = round(average_response_time, 2)
        average_response_size = sum([el['response_length'] for el in elements]) / float(len(elements))
        stats['average_response_size'] = round(average_response_size, 2)
        self.stats.append(stats)
        self.users.append(self.environment.runner.user_count)
        stats['error_details'] = self.errors
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
            - median_response_time_per_endpoint: float
            - avg_req_per_sec_per_endpoint: float
        """
        stats = {}
        timestamp = list(data.keys())[0]
        elements = data[timestamp]
        if len(locust_wrapper.environment.stats.entries) < 1:
            return None
        # prepare dict for stats
        errors = []
        number_of_requests = 0
        number_of_failures = 0
        number_of_none_requests = 0
        requests_per_second = 0
        failures_per_second = 0
        user_count = 0
        number_of_request_per_second = {}
        response_times_per_endpoint = {}
        response_times = []
        content_lengths = []
        for el in elements:
            user_count += el['user_count']
            number_of_requests += el['stats_total']['num_requests']
            number_of_failures += el['stats_total']['num_failures']
            requests_per_second += round(locust_wrapper.environment.stats.total.current_rps, 0)
            failures_per_second += round(locust_wrapper.environment.stats.total.current_fail_per_sec, 0)
            number_of_none_requests += el['stats_total']['num_none_requests']
            response_times.append(el['stats_total']['total_response_time'])
            content_lengths.append(el['stats_total']['total_content_length'])
            for endpoint in el["stats"]:
                current_env_endpoint = locust_wrapper.environment.stats.entries.get(
                    (endpoint["name"], endpoint["method"])
                )
                current_ep_rps = round(current_env_endpoint.current_rps)
                current_ep_times = current_env_endpoint.response_times
                number_of_request_per_second[endpoint["name"]] = current_ep_rps
                response_times_per_endpoint[endpoint["name"]] = current_ep_times
            if el['errors']:
                errors.extend(list(el['errors'].values()))

        if number_of_requests == 0:
            return None

        stats["requests"] = elements
        stats['execution_id'] = self.execution
        stats['timestamp'] = wrap_datetime.datetime.utcfromtimestamp(timestamp).isoformat()
        stats['number_of_successes'] = requests_per_second - failures_per_second
        stats['number_of_fails'] = failures_per_second
        stats['median_response_time_per_endpoint'] = parser.get_response_times_median_for_every_endpoint(
            response_times_per_endpoint
        )
        stats['avg_req_per_sec_per_endpoint'] = number_of_request_per_second

        number_of_users = self.environment.runner.user_count
        if number_of_users == 0 and user_count > 0:
            number_of_users = user_count
        stats['number_of_users'] = number_of_users

        number_of_errors = len(set(
            ['{0}/{1}/{2}'.format(error['method'], error['name'], error['error']) for error in errors]))
        stats['number_of_errors'] = number_of_errors

        stats['average_response_time'] = parser.get_avg_response_time(response_times, number_of_requests)
        stats['average_response_size'] = parser.get_avg_response_size(content_lengths, number_of_requests)

        self.stats.append(stats)
        self.users.append(self.environment.runner.user_count)
        stats['error_details'] = errors
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
                    self.stats_queue.append(stats)
                    save_to_database(stats)
            # send stats from queue if we lost connection during sending stats to database
            for stats in self.stats_queue:
                save_to_database(stats)
        # send first element from list to database if length of list more than 2
        elif len(self.dataset) > 0:
            first_element = self.dataset.pop(0)
            if WORKER_TYPE == 'master':
                stats = self.prepare_stats_by_interval_master(first_element)
            else:
                stats = self.prepare_stats_by_interval_common(first_element)
            if stats is not None:
                # add stats to queue for sending
                self.stats_queue.append(stats)
                # send as locust event
                save_to_database(stats)

    def push_event(self, data, event_type):
        # extracting errors for common cases (when WORKER_TYPE is not 'master' or 'slave')
        if event_type == 'failure':
            combined_key = '{0}/{1}/{2}'.format(data['request_type'], data['endpoint'], data['exception'])
            combined_key = wrap_re.sub(r' object at 0x\S*', '', combined_key)  # delete trash (obj address) from key
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
                combined_key = wrap_re.sub(r' object at 0x\S*', '', combined_key)  # delete trash (obj address) from key
                try:
                    _error = self.errors[combined_key]
                    _error['number_of_occurrences'] = error['occurences']
                except KeyError:
                    new_error = {combined_key: {
                        'execution_id': self.execution, 'number_of_occurrences': error['occurrences'],
                        'name': error['name'], 'error_type': error['method'], 'exception_data': error['error']
                    }}
                    self.errors.update(new_error)
        # push event to dataset for common cases
        now_timestamp = wrap_time.time()
        try:
            last_timestamp = list(self.dataset[-1].keys())[0]
        except IndexError:
            last_timestamp = now_timestamp

        if len(self.dataset) == 0:
            self.dataset.append({last_timestamp: []})

        if int(now_timestamp) - int(last_timestamp) < SENDING_INTERVAL_IN_SECONDS:
            self.dataset[-1][last_timestamp].append(data)
        else:
            self.dataset.append({now_timestamp: [data]})
            self.dataset_timestamps.append(int(now_timestamp))
        # try to save/send stats for interval
        self.save_stats()


locust_wrapper = LocustWrapper()


@wrap_events.request.add_listener
def request_handler(request_type, name, response_time, response_length, response, context, exception, start_time, url):
    """
    Handler for catching unsuccessful requests
    """
    event_type = 'failure' if exception is not None else 'success'
    received_data = {
        'execution_id': locust_wrapper.execution, 'endpoint': name, 'exception': str(exception),
        'request_type': request_type, 'response_length': response_length, 'response_time': float(response_time),
        'event_type': event_type, 'timestamp': int(wrap_time.time()),
    }
    locust_wrapper.push_event(received_data, event_type=event_type)


@wrap_events.quit.add_listener
def quitting_handler(exit_code):
    """
    Will be called before exiting test runner
    """
    if not locust_wrapper.is_finished and WORKER_TYPE == 'master':
        locust_wrapper.is_finished = True
        wrap_logger.info('Begin quit handler')
        locust_wrapper.end_execution = wrap_datetime.datetime.now()
        execution_update_data = {'end_locust': locust_wrapper.end_execution.isoformat()}
        locust_wrapper.bolt_api_client.update_execution(execution_id=EXECUTION_ID, data=execution_update_data)
        # save remaining data from 'dataset' list
        locust_wrapper.save_stats(send_all=True)
        sum_success = sum([s['number_of_successes'] for s in locust_wrapper.stats])
        wrap_logger.info(f'Number of success: {sum_success}. Number of errors {len(locust_wrapper.errors)}')
        wrap_logger.info(f'Count stats {len(locust_wrapper.stats)}')
        wrap_logger.info(f'Locust start: {locust_wrapper.start_execution}. '
                         f'Locust end: {locust_wrapper.end_execution}')
        wrap_logger.info(f'Dataset timestamps {locust_wrapper.dataset_timestamps}')
        # prepare and send error results to database
        for error_item in list(locust_wrapper.errors.items()):
            _, value = error_item
            locust_wrapper.bolt_api_client.insert_error_results(value)
        locust_wrapper.bolt_api_client.insert_endpoint_totals(EXECUTION_ID, locust_wrapper.environment.stats)
        locust_wrapper.bolt_api_client.update_execution(execution_id=EXECUTION_ID, data={'status': 'FINISHED'})
        locust_wrapper.bolt_api_client.terminate()
        wrap_logger.info('End quit handler')


@wrap_events.init.add_listener
def start_handler(environment, **kwargs):
    """
    Will be called before starting test runner
    """
    locust_wrapper.environment = environment
    if not locust_wrapper.is_started and isinstance(environment.runner, MasterRunner):
        wrap_logger.info('Begin start handler')
        wrap_logger.info(f'Started locust tests with execution {EXECUTION_ID}')
        locust_wrapper.bolt_api_client.insert_execution_instance({'status': 'READY', 'instance_type': 'load_tests'})
        locust_wrapper.start_execution = wrap_datetime.datetime.now()
        execution_update_data = {'start_locust': locust_wrapper.start_execution.isoformat(), 'status': 'RUNNING'}
        wrap_logger.info(f'Setting execution details to: {execution_update_data}')
        locust_wrapper.bolt_api_client.update_execution(execution_id=EXECUTION_ID, data=execution_update_data)
        if not locust_wrapper.dataset:
            locust_wrapper.dataset.append({locust_wrapper.start_execution.timestamp(): []})
            locust_wrapper.dataset_timestamps.append(int(locust_wrapper.start_execution.timestamp()))
        locust_wrapper.is_started = True
        wrap_logger.info('End start handler')


def save_to_database(data):
    """
    EventHook for sending aggregated results to database
    """
    if data is not None and data and WORKER_TYPE == 'master':
        try:
            locust_wrapper.bolt_api_client.insert_aggregated_results(data)
        except Exception as ex:
            wrap_logger.exception('Failed to insert aggregated results. Error ignored and execution continues.')
            wrap_logger.exception(ex)
            return
    try:
        locust_wrapper.stats_queue.remove(data)
    except ValueError:
        wrap_logger.info(f'Stats do not exist in queue {len(locust_wrapper.stats_queue)}')


@wrap_events.worker_report.add_listener
def report_from_slave_handler(client_id, data):
    """
    Using when WORKER_TYPE is 'master' for receiving stats from slaves.
    """
    if locust_wrapper.is_started and WORKER_TYPE == 'master':
        locust_wrapper.push_event(data=data, event_type=WORKER_TYPE)
