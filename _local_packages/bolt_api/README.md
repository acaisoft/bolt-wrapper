# ACAI⚡BOLT

### API

Deployment requirements:

* redis
* hasura
* `pip install -r requirements/core.txt`
* environment variables:
    * `PORT` 
    run wsgi on this
    * `HASURA_GRAPHQL_ACCESS_KEY` 
    to authorize as service-account with, hasura instance access_key must equal this
    * `HASURA_GQL` 
    full address of hasura, eg. http://localhost:8080/v1alpha1/graphql
    * `REDIS_HOST` and `REDIS_PORT` and `REDIS_DB`
* app configuration in `instance/conf.py`:
    * `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` 
    from https://console.cloud.google.com/apis/credentials/oauthclient/
    * `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` 
    from https://github.com/settings/applications/
    * `OAUTH_REDIRECT` 
    base address to redirect oauth responses to, 
    must be common for all oauth app providers, will most likely point to a frontend 
    address, eg.:
    if redirect address is configured in app is:  
    https://appfrontend.appspot.com/google/auth
    then OAUTH_REDIRECT will be https://appfrontend.appspot.com
    * `SECRET_KEY` 
    really secret, used for signing and verifying jwt tokens
    * `JWT_ALGORITHM` 
    defaults to `HS256`

### Startup sequence

#### Preparation

###### Hasura:

* set `HASURA_GRAPHQL_ACCESS_KEY` equal to api's
* execute `tools/encode_jwt_secret.py` and store result in `HASURA_GRAPHQL_JWT_SECRET`, eg.:
```
HASURA_GRAPHQL_JWT_SECRET: '{"type": "HS256", "key": "jwtsigningksecretkey"}'
```

###### DB:

Once hasura and db are up, go into `hasura` subfolder, 
adjust `endpoint` in `hasura/config.yaml` 
and execute hasura CLI tool:
```
/bin/hasura migrate apply
```

###### Services:

Start redis and db first, then api, then hasura.

Order is important.

Do not expose api graphql endpoint, patch it through hasura.