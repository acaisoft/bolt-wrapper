import typing
from bolt_api.upstream.base import BaseQuery, InputType


class ResultError(typing.NamedTuple, InputType):
    execution_id: str
    name: str
    error_type: str
    exception_data: str
    number_of_occurrences: str


class Query(BaseQuery):
    input_type = ResultError
