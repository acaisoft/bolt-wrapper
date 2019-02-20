import typing
from bolt_api.upstream.base import BaseQuery, InputType


class ConfigurationType(typing.NamedTuple, InputType):
    name: str
    description: str


class Query(BaseQuery):
    input_type = ConfigurationType
