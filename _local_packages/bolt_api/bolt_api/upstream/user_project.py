import typing
from bolt_api.upstream.base import BaseQuery, InputType


class UserProject(typing.NamedTuple, InputType):
    user_id: str
    project_id: str


class Query(BaseQuery):
    input_type = UserProject
