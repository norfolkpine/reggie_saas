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

### Using Django's Test Runner
To run tests using Django's test runner:

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

### Using Pytest (Recommended)
For more advanced testing features, we use pytest. First, install the required packages:

```bash
pip install pytest pytest-django pytest-cov factory-boy
```

#### Test Dependencies
The following packages are required for running tests:
- `pytest`: The main testing framework
- `pytest-django`: Django integration for pytest
- `pytest-cov`: For test coverage reporting
- `factory-boy`: For creating test fixtures and factories

#### Test Setup
1. Ensure your test database is created:
```bash
createdb test_bh_reggie
```

2. Run migrations on the test database:
```bash
python manage.py migrate --database=test_bh_reggie
```

To run all tests:
```bash
pytest
```

To run tests for a specific app:
```bash
pytest apps/docs/tests/
```

To run a specific test file:
```bash
pytest apps/docs/tests/documents/test_api_documents_create.py -v
```

To run tests with coverage report:
```bash
pytest --cov=apps
```

#### Test Database
The test database is configured to use PostgreSQL with the following settings:
- Database name: `test_bh_reggie`
- Uses the same credentials as your development database
- Test database is reused between test runs for better performance

#### Test Configuration
The test configuration is managed by:
- `pytest.ini`: Main pytest configuration
- `apps/docs/tests/conftest.py`: Test fixtures and database configuration

#### Initialise 
pytest --create-db
pytest --ds=bh_reggie.settings --create-db -v --capture=tee-sys
pytest --ds=bh_reggie.settings --reuse-db -v apps/authentication/tests/test_authentication.py
pytest apps/docs/tests/documents/test_api_documents_create.py -v



#### Common Test Issues
1. Missing test database: Ensure `test_bh_reggie` database exists
2. Missing dependencies: Make sure all test packages are installed
3. Migration issues: Run migrations on the test database
4. Factory errors: Check that factory-boy is installed and factories are properly configured

# Knowledge base
## Projects
Projects have their own knowledge base, it is created by using metadata and a knowledgebase_id field

## Agents
Agents parse files on upload and process this way, they dont need their own knowledgebases

add_document should add files
look at agentic_rag for how to add load etc.