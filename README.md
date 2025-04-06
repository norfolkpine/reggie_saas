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

# Requirements
pipreqs .
pipreqs . --force --encoding=utf-8 
cut -d= -f1 requirements.txt > requirements.in
pip-compile requirements.in
```

## Set up database

#### Requirement
- **pgvector** extension enabled for postgresql, read the documentation [here](https://github.com/pgvector/pgvector/blob/master/README.md)

Create a database named `bh_reggie`.

```
createdb bh_reggie
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
