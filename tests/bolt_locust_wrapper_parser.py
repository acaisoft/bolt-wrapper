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

from statistics import median
from bolt_logger import setup_custom_logger as wrap_setup_custom_logger

wrap_logger = wrap_setup_custom_logger(__name__)
wrap_logger.propagate = False


def get_response_times_median_for_every_endpoint(response_times_per_endpoint):
    """
    In every endpoint stats there are: 'response_times': { 420: 2, 430: 3,}
    To get median for single endpoint we need list like: [420, 420, 430, 430, 430]
    """
    for endpoint, value in response_times_per_endpoint.items():
        responses = []
        for time_value, counter in value.items():
            responses.extend([time_value for i in range(counter)])
        response_times_per_endpoint[endpoint] = median(responses)

    return response_times_per_endpoint


def get_number_of_request_per_second(number_of_request_per_second):
    if number_of_request_per_second:
        return {
            key: sum(value.values()) / len(value)
            for key, value in number_of_request_per_second.items()
        }
    return {}


def get_avg_response_time(response_times, number_of_requests):
    total_response_time = sum(response_times)

    try:
        return int(float(total_response_time) / number_of_requests)
    except (ZeroDivisionError, Exception) as ex:
        wrap_logger.info('Caught exception during calculating `average_response_time`')
        wrap_logger.info(f'{total_response_time} | {number_of_requests} | {ex}')
        return 0


def get_avg_response_size(content_lengths, number_of_requests):
    total_content_length = sum(content_lengths)

    try:
        return int(float(total_content_length) / number_of_requests)
    except (ZeroDivisionError, Exception) as ex:
        wrap_logger.info('Caught exception during calculating `average_response_size`')
        wrap_logger.info(f'{total_content_length} | {number_of_requests} | {ex}')
        return 0
