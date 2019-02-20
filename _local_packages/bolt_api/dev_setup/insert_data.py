import string
from datetime import datetime

from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
from bolt_api import upstream
from bolt_api.upstream.devclient import devclient


def insert_user(client: Client) -> str:
    objects = upstream.user.Query(client)
    ret = objects.insert(upstream.user.User(email="admin@acaisoft.net", active=True))
    return ret[0]['id']


def insert_execution_results(client: Client, execution_id):
    objects = upstream.execution_result.Query(client)
    data_set = []
    for i in range(1000):
        data_set.append(objects.input_type(
            execution_id=execution_id,
            endpoint="/stats/",
            exception="",
            request_type="GET",
            response_length=123,
            response_time=12.34,
            status="200",
            timestamp=1231231231321,
        ))
    objects.bulk_insert(data_set)


def insert_aggregated_results(client: Client, execution_id):
    objects = upstream.result_aggregate.Query(client)
    data = objects.input_type(
        execution_id=execution_id,
        fail=0,
        av_resp_time=23.45,
        succes=123,
        error=124,
        av_size=200,
        timestamp=1231231231321,
    )
    objects.insert(data)


def insert_distribution_results(client, execution_id):
    objects = upstream.result_distribution.Query(client)
    data = upstream.result_distribution.ResultDistribution(
        execution_id=execution_id,
        start=datetime.now(),
        end=datetime.now(),
        request_result={"type": "request", "result": "ok"},
        distribution_result={"type": "distribution", "result": 400},
    )
    objects.insert(data)


def insert_project(client):
    ret = upstream.project.Query(client).insert(upstream.project.Project(name="pro1", contact="admin@adm.in"))
    return ret[0]['id']


def insert_repository(client):
    o = upstream.repository.Query(client)
    ret = o.insert(upstream.repository.Repository(name="repo 1", url="http://url.url/url", username="root", password="password"))
    return ret[0]['id']


def insert_configuration(client, project, repository):
    ret = upstream.configuration.Query(client).insert(
        upstream.configuration.Conf(name="conf 1", repository_id=repository, project_id=project)
    )
    return ret[0]['id']


def insert_execution(client, configuration):
    query = string.Template('''mutation{insert_execution(objects:[{
    configuration_id:"$configuration",
    status:"running",
    }]) {returning {id}}}''').substitute(configuration=configuration)
    ret = client.execute(gql(query))
    return ret['insert_execution']['returning'][0]['id']


def insert_data(client: Client):
    # insert_users(client)
    admin_user = insert_user(client)
    project = insert_project(client)
    repository = insert_repository(client)
    configuration = insert_configuration(client, project, repository)
    execution = insert_execution(client, configuration)
    insert_execution_results(client, execution)
    insert_aggregated_results(client, execution)
    insert_distribution_results(client, execution)


def purge_data(client: Client):
    upstream.user.Query(client).purge()


def new_client() -> Client:
    return devclient()


if __name__ == "__main__":
    cl = new_client()
    purge_data(cl)
    insert_data(cl)
