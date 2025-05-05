# Ben Heath SaaS

BH Blockchain Analytics Platform

## Installation
Setup a virtualenv and install requirements
(this example uses [virtualenvwrapper](https://virtualenvwrapper.readthedocs.io/en/latest/)):

```bash
# mkvirtualenv bh_reggie -p python3.12
python3.12 -m venv venv
source venv/bin/activate
pip install -r dev-requirements.txt

# Requirements\
pip install pip-tools
pipreqs .
pipreqs . --force --encoding=utf-8 
cut -d= -f1 requirements.txt > requirements.in
pip-compile requirements.in
pre-commit run --show-diff-on-failure --color=always --all-files
```

## Set up Cloud Run API Key

The Cloud Run ingestion service needs an API key to communicate with the Django backend. Generate one using:

```bash
python manage.py create_cloud_run_api_key
```

This will:
1. Create a system user for the Cloud Run service
2. Generate an API key for that user
3. Output the key that should be added to your Cloud Run service's environment variables

Add the generated API key to your Cloud Run service's environment variables:
```
DJANGO_API_KEY=your-generated-api-key
```

## API Key Authentication Details

### Authentication Format
Both services use the following header format for API key authentication:
```
Authorization: Api-Key {key}
```

### Testing API Key Setup
You can verify the API key configuration using the following command:

```bash
python manage.py shell -c "from django.contrib.auth import get_user_model; from apps.api.models import UserAPIKey; User = get_user_model(); system_user = User.objects.get(email='cloud-run-service@system.local'); api_key = UserAPIKey.objects.filter(user=system_user, name='Cloud Run Ingestion Service', revoked=False).first(); print(f'API Key exists: {bool(api_key)}\nAPI Key prefix: {api_key.prefix if api_key else None}\nAPI Key name: {api_key.name if api_key else None}')"
```

This command will output:
- Whether the API key exists
- The API key prefix
- The API key name

### Troubleshooting
If authentication issues occur:
1. Verify the API key exists and is not revoked using the test command above
2. Ensure the Cloud Run service's `DJANGO_API_KEY` environment variable matches the generated key
3. Check that both services are using the correct "Api-Key" prefix in the Authorization header

## Set up database

#### Requirement
- **pgvector** extension enabled for postgresql, read the documentation [here](https://github.com/pgvector/pgvector/blob/master/README.md)

Create a database named `bh_reggie`.

```createdb bh_reggie
```

Create database migrations (optional):

```
python manage.py makemigrations
```

Create database tables:

```
python manage.py migrate
```

## Running server

```bash
python manage.py runserver
```

## Building front-end

To build JavaScript and CSS files, first install npm packages:

```bash
npm install
```

Then build (and watch for changes locally):

```bash
npm run dev-watch
```

## Running Celery

Celery can be used to run background tasks.

Celery requires [Redis](https://redis.io/) as a message broker, so make sure
it is installed and running.

You can run it using:

```bash
celery -A bh_reggie worker -l INFO --pool=solo
```

Or with celery beat (for scheduled tasks):

```bash
celery -A bh_reggie worker -l INFO -B --pool=solo
```

Note: Using the `solo` pool is recommended for development but not for production.

## Updating translations

```bash
python manage.py makemessages --all --ignore node_modules --ignore .venv
python manage.py makemessages -d djangojs --all --ignore node_modules --ignore .venv
python manage.py compilemessages --ignore .venv
```

## Google Authentication Setup

To setup Google Authentication, follow the [instructions here](https://docs.allauth.org/en/latest/socialaccount/providers/google.html).

## Installing Git commit hooks

To install the Git commit hooks run the following:

```shell
$ pre-commit install --install-hooks
# Run checks
pre-commit run --show-diff-on-failure --color=always --all-files
```


Once these are installed they will be run on every commit.

For more information see the [docs](https://docs.saaspegasus.com/code-structure.html#code-formatting).

## Running Tests

To run tests:

```bash
python manage.py test
```

Or to test a specific app/module:

```bash
python manage.py test apps.utils.tests.test_slugs
```

On Linux-based systems you can watch for changes using the following:

```bash
find . -name '*.py' | entr python manage.py test apps.utils.tests.test_slugs
```


# Knowledge base
## Projects
Projects have their own knowledge base, it is created by using metadata and a knowledgebase_id field

## Agents
Agents parse files on upload and process this way, they dont need their own knowledgebases

add_document should add files
look at agentic_rag for how to add load etc.