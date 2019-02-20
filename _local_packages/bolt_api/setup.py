from setuptools import setup

setup(
    name='boltapi',
    version='0.2',
    packages=['bolt_api', 'bolt_api.upstream', 'bolt_api.upstream.tests', 'dev_setup', 'hasura', 'hasura.migrations'],
    url='https://bitbucket.org/acaisoft/bolt-api/',
    license='',
    author='piotr',
    author_email='',
    description='',
    install_requires=[
        'graphene',
        'gql',
        'Flask',
        'requests',
    ],
)
