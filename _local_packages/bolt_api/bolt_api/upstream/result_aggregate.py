import typing
from datetime import datetime

from bolt_api.upstream.base import BaseQuery, InputType


class ResultAggregate(typing.NamedTuple, InputType):
    execution_id: str
    number_of_fails: str
    number_of_successes: str
    number_of_errors: str
    average_response_time: str
    average_response_size: str
    timestamp: datetime


class Query(BaseQuery):
    input_type = ResultAggregate
