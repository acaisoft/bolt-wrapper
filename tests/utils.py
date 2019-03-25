import json

from typing import Dict
from string import Template

from exceptions import StatusCodeException, TimeException, BodyTextEqualException, BodyTextContainsException


def _failed_with_response_code(_assert, response):
    return True if str(response.status_code) != _assert['value'] else False


def _failed_with_response_time(_assert, response):
    response_time_in_milliseconds = response.elapsed.total_seconds() * 1000
    return True if int(response_time_in_milliseconds) > int(_assert['value']) else False


def _failed_with_body_text_equal(_assert, response):
    return True if _assert['value'] != response.text else False


def _failed_with_body_text_contains(_assert, response):
    return True if _assert['value'] not in response.text else False


def check_response_for_failure(_assert, response):
    if _assert['assert_type'] == 'response_code' and _failed_with_response_code(_assert, response):
        return StatusCodeException(_assert['message'])
    elif _assert['assert_type'] == 'response_time' and _failed_with_response_time(_assert, response):
        return TimeException(_assert['message'])
    elif _assert['assert_type'] == 'body_text_equal' and _failed_with_body_text_equal(_assert, response):
        return BodyTextEqualException(_assert['message'])
    elif _assert['assert_type'] == 'body_text_contains' and _failed_with_body_text_contains(_assert, response):
        return BodyTextContainsException(_assert['message'])
    else:
        return None


def get_kwargs_for_endpoint(endpoint, global_headers):
    kwargs = {}
    if 'name' in endpoint.keys():
        kwargs.update({'name': endpoint['name']})
    if 'payload' in endpoint.keys():
        kwargs.update({'data': endpoint['payload']})
    if 'headers' in endpoint.keys() or global_headers:
        combined_headers = {}
        if global_headers:
            combined_headers.update(global_headers)
        if 'headers' in endpoint.keys():
            combined_headers.update(endpoint['headers'])
        kwargs.update({'headers': combined_headers})
    return kwargs


def get_variable_from_dict_by_keys(data: dict, keys: list, first_iteration=True):
    if first_iteration and (not data or not keys):
        return None
    try:
        key = keys.pop(0)
    except IndexError:
        return data
    else:
        try:
            _data = data[key]
        except KeyError:
            return None
        return get_variable_from_dict_by_keys(_data, keys, first_iteration=False)


def extract_variables_from_response(actions, response):
    variables = {}
    for action in actions or []:
        if action['location'] == 'headers':
            dict_data = response.headers
        elif action['location'] == 'cookies':
            dict_data = response.cookies.get_dict()
        elif action['location'] == 'response':
            try:
                dict_data = response.json()
            except (json.JSONDecodeError, ValueError):
                continue
        else:
            continue
        # extract variable from response data
        variable_keys = action['variable_path'].split('.')
        variable_value = get_variable_from_dict_by_keys(dict_data, variable_keys)
        variables.update({action['variable_name']: variable_value})
    return variables


def render_variables_to_kwargs(variables: Dict, **kwargs):
    """
    Example of usage:
        >>> my_kwargs = {'greeting': 'Hello ${name}', 'list': [1, 2 , 'My list ${list_value}']}
        >>> my_variables = {'name': 'Tom', 'list_value': 3}
        >>> render_variables_to_kwargs(my_variables, **my_kwargs)
        >>> {'greeting': 'Hello Tom', 'list': [1, 2, 'My list 3']}
    """
    template = Template(json.dumps(kwargs))
    rendered = template.safe_substitute(**variables)
    return json.loads(rendered)


def task_factory(method, url, asserts, actions, **kwargs):
    """
    Factory function which returning another function instance as locust task
    """
    def func(locust):
        updated_kwargs = render_variables_to_kwargs(locust.client.variables, **kwargs)
        with locust.client.request(method, url, catch_response=True, **updated_kwargs) as response:
            # handle actions
            variables = extract_variables_from_response(actions, response)
            if variables:
                locust.client.variables.update(variables)
            # handle failures
            endpoint_failed = False
            for _assert in asserts or []:
                exception = check_response_for_failure(_assert, response)
                if exception is not None:
                    endpoint_failed = True
                    response.failure(exception)
            if not endpoint_failed:
                response.success()
    return func


def prepare_locust_data(data: Dict):
    """
    Preparing locust tasks/functions as 'list' or 'dict'
    """
    # extract variables from JSON/Dict data
    test_type = data['test_type']
    endpoints = data['endpoints']
    global_headers = data.get('global_headers')
    setup = data.get('setup')
    teardown = data.get('teardown')
    on_start = data.get('on_start')
    on_stop = data.get('on_stop')
    # preparing locust tasks
    tasks = [] if test_type == 'sequence' else {}
    for endpoint in endpoints:
        kwargs = get_kwargs_for_endpoint(endpoint, global_headers)
        task_instance = task_factory(
            endpoint['method'], endpoint['url'], endpoint.get('asserts'), endpoint.get('actions'), **kwargs)
        # if test type is 'sequence' we using list for storing tasks
        if isinstance(tasks, list):
            tasks.append(task_instance)
        # if test type is 'set' we using dict for storing tasks
        elif isinstance(tasks, dict):
            tasks.update({task_instance: endpoint['task_value']})
    return tasks, setup, teardown, on_start, on_stop
