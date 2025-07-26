# Ben Heath SaaS

BH Crypto

## Installation
Setup a virtualenv and install requirements
(this example uses [virtualenvwrapper](https://virtualenvwrapper.readthedocs.io/en/latest/)):

```bash
mkvirtualenv bh_crypto -p python3.12
pip install -r dev-requirements.txt
```

## Set up database

Create a database named `bh_crypto`.

```
createdb bh_crypto
```

Create database migrations:

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
celery -A bh_crypto worker -l INFO --pool=solo
```

Or with celery beat (for scheduled tasks):

```bash
celery -A bh_crypto worker -l INFO -B --pool=solo
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
