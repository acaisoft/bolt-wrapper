import unittest

from bolt_api.upstream import user


class DataTestCase(unittest.TestCase):

    def test_data(self):
        data_in = user.User(email="jan@kowal.pl", active=True)
        data_out = user.Query.serialize(data_in)
        self.assertEqual(data_out, '''{
email:"jan@kowal.pl",
active:"true",
},
''')
