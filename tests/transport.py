from gql.transport.requests import RequestsHTTPTransport
import requests
from graphql.execution import ExecutionResult
from graphql.language.printer import print_ast


class WrappedTransport(RequestsHTTPTransport):
    no_keep_alive = False

    def __init__(self, *args, **kwargs):
        self.no_keep_alive = kwargs.pop('no_keep_alive', False)
        super().__init__(*args, **kwargs)

        if self.no_keep_alive:
            self.headers['Connection'] = 'close'

    def execute(self, document, variable_values=None, timeout=None):
        query_str = print_ast(document)
        payload = {
            'query': query_str,
            'variables': variable_values or {}
        }

        data_key = 'json' if self.use_json else 'data'
        post_args = {
            'headers': self.headers,
            'auth': self.auth,
            'timeout': timeout or self.default_timeout,
            data_key: payload
        }
        request = requests.post(self.url, **post_args)
        if request.status_code >= 500:
            request.raise_for_status()

        result = request.json()
        assert 'errors' in result or 'data' in result, 'Received non-compatible response "{}"'.format(result)
        return ExecutionResult(
            errors=result.get('errors'),
            data=result.get('data')
        )
