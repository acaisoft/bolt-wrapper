import typing
from bolt_api.upstream.base import BaseQuery, InputType


class Repository(typing.NamedTuple, InputType):
    name: str
    url: str
    username: str
    password: str


class Query(BaseQuery):
    input_type = Repository
