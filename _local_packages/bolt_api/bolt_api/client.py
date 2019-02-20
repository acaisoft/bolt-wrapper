import string

from bolt_api import upstream
from gql import gql


class BoltAPIClient(object):
    """
    GraphQL client for communication with Bolt database
    """

    def __init__(self, gql_client):
        self._gcl_client = gql_client

    def insert_user(self, data) -> str:
        """
        :param data: Dict:
            - email: str
            - active: bool
        :return: id
        """
        objects = upstream.user.Query(self._gcl_client)
        ret = objects.insert(upstream.user.User(**data))
        return ret[0]['id']

    def insert_aggregated_results(self, data):
        """
        :param data: Dict:
            - execution_id: uuid
            - number_of_fails: int
            - number_of_successes: int
            - number_of_errors: int
            - average_response_time: float
            - average_response_size: float
            - timestamp: datetime
        :return: id
        """
        objects = upstream.result_aggregate.Query(self._gcl_client)
        data = objects.input_type(**data)
        response = objects.insert(data)
        return response[0]['id']

    def insert_distribution_results(self, data):
        """
        :param data: Dict:
            - execution_id: uuid
            - start: datetime
            - end: datetime
            - request_result: struct/json
            - distribution_result: struct/json
        :return: id
        """
        objects = upstream.result_distribution.Query(self._gcl_client)
        data = upstream.result_distribution.ResultDistribution(**data)
        response = objects.insert(data)
        return response[0]['id']

    def insert_error_results(self, data):
        """
        :param data: Dict:
            - execution_id: uuid
            - name: str
            - error_type: str
            - exception_data: str
            - number_of_occurrences: int
        :return: id
        """
        objects = upstream.result_error.Query(self._gcl_client)
        data = upstream.result_error.ResultError(**data)
        response = objects.insert(data)
        return response[0]['id']

    def insert_project(self, data):
        """
        :param data: Dict:
            - name: str
            - contact: str
        :return: id
        """
        ret = upstream.project.Query(self._gcl_client).insert(upstream.project.Project(**data))
        return ret[0]['id']

    def insert_repository(self, data):
        """
        :param data: Dict:
            - name: str
            - url: str
            - username: str
            - password: str
        :return: id
        """
        o = upstream.repository.Query(self._gcl_client)
        ret = o.insert(upstream.repository.Repository(**data))
        return ret[0]['id']

    def insert_configuration_type(self, data):
        """
        :param data: Dict:
            - name: str
            - description: str
        :return: id
        """
        query = upstream.configuration_type.Query(self._gcl_client)
        result = query.insert(upstream.configuration_type.ConfigurationType(**data))
        return result[0]['id']

    def insert_configuration(self, data):
        """
        :param data: Dict:
            - name: str
            - project_id: uuid
            - repository_id: uuid
        :return: id
        """
        ret = upstream.configuration.Query(self._gcl_client).insert(
            upstream.configuration.Conf(**data)
        )
        return ret[0]['id']

    def insert_execution(self, data):
        """
        :param data: Dict:
            - configuration: uuid
        :return: id
        """
        query = string.Template('''mutation{insert_execution(objects:[{
        configuration_id:"$configuration",
        status:"running",
        }]) {returning {id}}}''').substitute(**data)
        ret = self._gcl_client.execute(gql(query))
        return ret['insert_execution']['returning'][0]['id']
