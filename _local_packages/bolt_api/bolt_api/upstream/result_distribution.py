import typing
from datetime import datetime

from bolt_api.upstream.base import BaseQuery, InputType


class ResultDistribution(typing.NamedTuple, InputType):
    execution_id: str
    start: datetime
    end: datetime
    request_result: typing.Any
    distribution_result: typing.Any


class Query(BaseQuery):
    input_type = ResultDistribution
