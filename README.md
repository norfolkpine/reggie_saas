# Ben Heath SaaS

BH Crypto

## Installation
Setup a virtualenv and install requirements
(this example uses [virtualenvwrapper](https://virtualenvwrapper.readthedocs.io/en/latest/)):

```bash
# mkvirtualenv bh_reggie -p python3.12
python -m venv venv
source venv/bin/activate
pip install -r dev-requirements.txt

# Requirements\
pip install pip-tools
pipreqs .
pipreqs . --force --encoding=utf-8 
cut -d= -f1 requirements.txt > requirements.in
pip-compile requirements/requirements.in
# Install Black for code formatting (configured to match project style)
pip install black
# Format code with Black (120 char lines, double quotes)
black .
# Run pre-commit checks
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
```
docker-compose -f docker-compose-dependencies.yml up
```

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

## Code Quality and Linting

This project uses [Ruff](https://docs.astral.sh/ruff/) for Python code linting and formatting. Ruff is configured via pre-commit hooks and can also be run manually.

**Important**: This project is configured to use both Black and Ruff for formatting. Black is configured to use 120 character lines and double quotes to match the project's style. Both tools are configured to work together without conflicts.

### Manual Linting and Formatting

To check for code quality issues and format code:

```bash
# Activate virtual environment first
source venv/bin/activate

# Format code with Black (120 char lines, double quotes)
black .

# Check for specific issues (line length, nested if statements, etc.)
python -m ruff check bh_reggie/settings.py --select E501,SIM102

# Check entire project for all issues
python -m ruff check .

# Check and automatically fix issues where possible
python -m ruff check --fix .

# Format code with Ruff (alternative to Black)
python -m ruff format .
```

### Common Linting Issues

- **E501**: Line too long (max 120 characters)
- **SIM102**: Nested if statements (use `and` operator instead)
- **F401**: Unused imports
- **E501**: Line length violations

### Pre-commit Integration

The project includes pre-commit hooks that automatically run Ruff on staged files. To ensure code quality:

```bash
# Install pre-commit hooks
pre-commit install --install-hooks

# Run on all files
pre-commit run --all-files

# Run specific hook
pre-commit run ruff --all-files

### Troubleshooting Formatting Conflicts

If you experience files being repeatedly modified when running formatters, ensure both tools are using the same configuration:

1. **Verify Black configuration**:
   ```bash
   black --version
   black --help | grep "line-length"
   ```

2. **Check that both tools use the same settings**:
   - Black: 120 character lines, double quotes
   - Ruff: 120 character lines, double quotes

3. **Use the recommended workflow**:
   ```bash
   # First format with Black
   black .
   
   # Then run pre-commit (which uses Ruff)
   pre-commit run --all-files
   ```

4. **Reset pre-commit cache** if issues persist:
   ```bash
   pre-commit clean
   pre-commit install --install-hooks
   ```
```

## Updating Dependencies & Security Patching

To keep dependencies up to date and apply security patches while ensuring compatibility, follow these steps:

1. **Update the Input Files**
   - Edit the `.in` files in the `requirements/` directory (`requirements.in`, `dev-requirements.in`, `prod-requirements.in`) to bump specific packages or leave versions unpinned to get the latest.

2. **Compile Updated Requirements**
   - Use pip-tools to recompile the `.txt` files from the `.in` files. This will resolve and lock all dependencies to compatible versions.
   - To update all packages to the latest compatible versions, use the `--upgrade` flag:

   ```sh
   pip-compile --upgrade requirements/requirements.in
   pip-compile --upgrade requirements/dev-requirements.in
   pip-compile --upgrade requirements/prod-requirements.in
   ```

   - This will update `requirements.txt`, `dev-requirements.txt`, and `prod-requirements.txt` with the latest compatible versions.

3. **Test Compatibility**
   - After updating, install the new requirements in a fresh virtual environment:
     ```sh
     python -m venv venv
     source venv/bin/activate
     pip install -r requirements/dev-requirements.txt
     ```
   - Run your test suite and manual checks to ensure nothing is broken.

4. **Address Any Issues**
   - If you encounter incompatibilities, pin or adjust versions in your `.in` files until everything works.

5. **Commit and Deploy**
   - Once tests pass, commit the updated `.in` and `.txt` files and deploy as usual.

**Note:**
- Always review the diff of your requirements files to see what changed.
- If you use `uv` for compiling, you can use:
  ```sh
  uv pip compile --upgrade requirements/prod-requirements.in -o requirements/prod-requirements.txt
  ```

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

** default schema must = ai **

## Environment Variables

### Required Environment Variables

Create a `.env` file in the root directory with the following variables:

#### Database Configuration
```bash
# Database settings
DATABASE_URL=postgresql://username:password@localhost:5432/bh_reggie
# Or individual database settings
DJANGO_DATABASE_NAME=bh_reggie
DJANGO_DATABASE_USER=your_db_user
DJANGO_DATABASE_PASSWORD=your_db_password
DJANGO_DATABASE_HOST=localhost
DJANGO_DATABASE_PORT=5432
```

#### Security Settings
```bash
# Django secret key (generate a new one for production)
SECRET_KEY=your-secret-key-here

# JWT signing key (generate a new one for production)
SIMPLE_JWT_SIGNING_KEY=your-jwt-signing-key-here

# CSRF settings
CSRF_COOKIE_SECURE=False  # Set to True in production
CSRF_COOKIE_SAMESITE=None
CSRF_COOKIE_DOMAIN=None
```

#### Mobile App Authentication
```bash
# Mobile app identifiers (comma-separated)
MOBILE_APP_IDS=com.benheath.reggie.ios,com.benheath.reggie.android

# Minimum app version required
MOBILE_APP_MIN_VERSION=1.0.0

# JWT authentication settings
JWT_AUTH_SECURE=True
JWT_AUTH_SAMESITE=Lax
```

#### Redis Configuration
```bash
# Redis for caching and Celery
REDIS_URL=redis://localhost:6379/0
REDIS_CACHE_URL=redis://localhost:6379/2
```

#### Email Configuration
```bash
# Email settings
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=hello@benheath.com.au
SERVER_EMAIL=noreply@localhost:8000
```

#### External Services (Optional)
```bash
# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_SECRET_ID=your-google-secret

# Stripe (for payments)
STRIPE_LIVE_PUBLIC_KEY=pk_live_***
STRIPE_LIVE_SECRET_KEY=sk_live_***
STRIPE_TEST_PUBLIC_KEY=pk_test_***
STRIPE_TEST_SECRET_KEY=sk_test_***
STRIPE_LIVE_MODE=False
DJSTRIPE_WEBHOOK_SECRET=whsec_***

# OpenAI (for AI features)
OPENAI_API_KEY=your-openai-api-key
AI_CHAT_OPENAI_MODEL=gpt-4o

# Slack Integration
SLACK_BOT_TOKEN=your-slack-bot-token
SLACK_SIGNING_SECRET=your-slack-signing-secret
SLACK_CLIENT_ID=your-slack-client-id
SLACK_CLIENT_SECRET=your-slack-client-secret
```

### Mobile App Authentication

The application supports secure mobile app authentication using JWT tokens. Mobile apps must include specific headers for authentication:

#### Required Headers for Mobile Apps
- `X-Mobile-App-ID`: Your app's bundle identifier (e.g., `com.benheath.reggie.ios`)
- `X-Mobile-App-Version`: App version (e.g., `1.0.0`)
- `X-Device-ID`: Unique device identifier

#### Authentication Endpoints
- **Login**: `POST /api/auth/mobile/login/`
- **Token Refresh**: `POST /api/auth/mobile/token/refresh/`
- **Standard JWT**: `POST /api/auth/jwt/token/`

#### Example Mobile App Request
```swift
// iOS Swift example
let request = URLRequest(url: URL(string: "https://your-domain.com/api/auth/mobile/login/")!)
request.setValue("application/json", forHTTPHeaderField: "Content-Type")
request.setValue("com.benheath.reggie.ios", forHTTPHeaderField: "X-Mobile-App-ID")
request.setValue("1.0.0", forHTTPHeaderField: "X-Mobile-App-Version")
request.setValue(UIDevice.current.identifierForVendor?.uuidString, forHTTPHeaderField: "X-Device-ID")

let body = ["email": "user@example.com", "password": "password"]
request.httpBody = try? JSONSerialization.data(withJSONObject: body)
```

#### Security Features
- Rate limiting (max 5 login attempts per device/IP)
- Input validation and sanitization
- JWT token authentication with refresh tokens
- Mobile app identity validation
- User activity logging

### Development vs Production

#### Development Settings
```bash
DEBUG=True
ALLOWED_HOSTS=*
CSRF_COOKIE_SECURE=False
SESSION_COOKIE_SECURE=False
```

#### Production Settings
```bash
DEBUG=False
ALLOWED_HOSTS=your-domain.com,www.your-domain.com
CSRF_COOKIE_SECURE=True
SESSION_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True
```

## Database Setup

Run the SQL command on file `init_pg_trm.sql` to create the pg_trgm extension and fuzzystrmatch extension
