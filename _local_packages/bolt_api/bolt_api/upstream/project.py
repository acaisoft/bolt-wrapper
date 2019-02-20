import typing
from bolt_api.upstream.base import BaseQuery, InputType


class Project(typing.NamedTuple, InputType):
    name: str
    contact: str


class Query(BaseQuery):
    input_type = Project
