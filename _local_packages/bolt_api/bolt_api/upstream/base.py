import json
import string
import time
import typing
import datetime

from gql import gql, Client


class InputType(typing.NamedTuple):
    id: str


class BaseQuery(object):
    client = None
    name = None
    bulk_size = 200
    input_type: InputType

    query_template = '''
    query {
        %(ityp)s %(args)s { %(returning)s } 
    }'''

    mutation_template = '''
    mutation {
        %(op)s_%(ityp)s(objects: [ %(objects)s ]) { returning { %(returning)s } } 
    }'''

    deletion_template = '''
    mutation {
        delete_%(ityp)s(where:{id:{%(op)s: "%(id)s"}}) { affected_rows }
    }'''

    def __init__(self, client: Client):
        self.client = client
        self.name = self.name or self.__class__.__module__.split('.')[-1]

    def execute(self, query):
        """
        Execute any query
        :param query: the query
        :return: response[<query_name>]["returning"] list
        """
        print(query)
        start = time.time()
        ret = self.client.execute(gql(query))
        print('query took %.2f seconds' % (time.time() - start))
        # unwrap the pointless (in case of single-query) <query-name>-returning keys
        for k in ret:
            query_type_result = ret[k]
            if isinstance(query_type_result, list):
                return query_type_result
            for l in query_type_result:
                return query_type_result[l]

    def query(self, where: str = None, returning: str = None):
        if where and where[0] != "(":
            raise RuntimeError("query WHERE clause must be enclosed in ( braces )")
        query = self.query_template % {
            'ityp': self.name,
            'args': where or "",
            'returning': returning or 'id',
        }
        return self.execute(query)

    def purge(self):
        query = self.deletion_template % {
            'ityp': self.name,
            'op': '_neq',
            'id': '00000000-0000-0000-0000-000000000000',
        }
        return self.execute(query)

    def insert(self, objects_str_or_type, returning=None):
        obj = self.serialize(objects_str_or_type)
        return self.insert_string(obj, returning)

    def bulk_insert(self, data):
        bulk = ""
        bulked = self.bulk_size

        for i in iter(data):
            if bulked > 0:
                bulk += self.serialize(i)
                bulked -= 1
            else:
                self.insert_string(bulk)
                bulk = ""
                bulked = self.bulk_size

        if bulk:
            return self.insert_string(bulk)

    def insert_string(self, objects_string: string, returning=None):
        query = self.mutation_template % {
            'op': 'insert',
            'ityp': self.name,
            'objects': objects_string,
            'returning': returning or 'id',
        }
        return self.execute(query)

    @staticmethod
    def serialize(input_type_object):
        out = '{\n'
        for i, f in enumerate(input_type_object._fields):
            t = input_type_object._field_types[f]
            if t == str:
                out += '''%(f)s:"%(v)s",\n''' % {'f': f, 'v': input_type_object[i]}
            elif t == bool:
                out += '''%(f)s:%(v)s,\n''' % {'f': f, 'v': str(input_type_object[i]).lower()}
            elif t in (dict, typing.Any):
                v = json.dumps(input_type_object[i])
                out += '''%(f)s:"%(v)s",\n''' % {'f': f, 'v': v.replace('"', r'\"')}
            elif t == datetime.datetime or t == datetime.date:
                v = input_type_object[i].isoformat()
                out += '''%(f)s:"%(v)s",\n''' % {'f': f, 'v': v}
            else:
                out += '''%(f)s:%(v)s,\n''' % {'f': f, 'v': str(input_type_object[i])}
        return out + '},\n'
