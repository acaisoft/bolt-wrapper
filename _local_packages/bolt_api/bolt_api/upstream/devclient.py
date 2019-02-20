import logging
import os

from gql import Client
from gql.transport.requests import RequestsHTTPTransport


_client = None


def devclient():
    global _client
    if not _client:
        target = os.environ.get('HASURA_GQL', 'http://localhost:8080/v1alpha1/graphql')
        access_key = os.environ.get('HASURA_GRAPHQL_ACCESS_KEY', 'devaccess')
        assert access_key, 'HASURA_GRAPHQL_ACCESS_KEY is not set'
        logging.info("connecting hasura at %s", target)
        _client = Client(
            retries=0,
            transport=RequestsHTTPTransport(
                url=target,
                use_json=True,
                headers={'X-Hasura-Access-Key': access_key},
            )
        )
    return _client
