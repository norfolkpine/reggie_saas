"""
Django settings for Ben Heath SaaS project.
.
For more information on this file, see
https://docs.djangoproject.com/en/stable/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/stable/ref/settings/
"""

import io
import os
import sys
from datetime import timedelta
from pathlib import Path

import environ
import requests
from configurations import Configuration, values
from django.utils.translation import gettext_lazy
from google.cloud import secretmanager

# Build paths inside the project like this: BASE_DIR / "subdir".
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
env.read_env(os.path.join(BASE_DIR, ".env"))  # <-- This is required!

# PGVector Table Prefix Setting
PGVECTOR_TABLE_PREFIX = env("PGVECTOR_TABLE_PREFIX", default="_vector_table")


def is_gcp_vm():
    try:
        response = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/",
            headers={"Metadata-Flavor": "Google"},
            timeout=2,
        )
        result = response.status_code == 200
        print(f"SETTINGS.PY DEBUG: is_gcp_vm() returning: {result} (status_code: {response.status_code})", flush=True)
        return result
    except requests.exceptions.RequestException as e_gcp_check:
        print(f"SETTINGS.PY DEBUG: is_gcp_vm() exception: {e_gcp_check}", flush=True)
        return False


gcp_check_result = is_gcp_vm()
print(f"SETTINGS.PY DEBUG: Result of is_gcp_vm() check: {gcp_check_result}", flush=True)
if gcp_check_result:
    try:
        client = secretmanager.SecretManagerServiceClient()
        secret_name = "projects/537698701121/secrets/bh-reggie-test/versions/latest"
        payload = client.access_secret_version(request={"name": secret_name}).payload.data.decode("UTF-8")
        env.read_env(io.StringIO(payload))
    except Exception as e_secret_load:
        print(f"SETTINGS.PY DEBUG: Error loading secrets from Secret Manager: {e_secret_load}", flush=True)
        # In a production app, you might want to log this error properly.
        # For now, if secrets fail to load, the app will rely on .env or defaults.
        # Consider adding logging here if this becomes an issue.
        pass
else:
    print(
        "SETTINGS.PY DEBUG: Not a GCP VM (is_gcp_vm() returned False or None), attempting to load from .env file.",
        flush=True,
    )
    # Not a GCP VM, attempt to load from .env file
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        env.read_env(env_path)
    # else:
    # .env file does not exist. Environment variables might be set externally,
    # or the application will rely on default values defined in the code.
    # pass

# === Google Cloud Storage bucket names ===
# Used for separating static files and uploaded media
GS_STATIC_BUCKET_NAME = env("GS_STATIC_BUCKET_NAME", default="bh-reggie-static")
GS_MEDIA_BUCKET_NAME = env("GS_MEDIA_BUCKET_NAME", default="bh-reggie-media")

# Ensure DATABASE_URL is set, constructing it from individual components if necessary
# print("DJANGO_DATABASE_PORT from os.environ:", os.environ.get("DJANGO_DATABASE_PORT"))
# print("DJANGO_DATABASE_PORT from env:", env("DJANGO_DATABASE_PORT", default="not set"))


# Tepat sebelum blok fallback
database_url = env('DATABASE_URL', default=None)
if database_url:
    # Mask the password in the URL for security
    try:
        # Parse the URL to properly mask username and password
        if '@' in database_url:
            # Split at @ to separate credentials from host
            credentials_part, host_part = database_url.split('@', 1)
            # Split credentials at : to separate username and password
            if '://' in credentials_part:
                protocol, credentials = credentials_part.split('://', 1)
                if ':' in credentials:
                    username, password = credentials.split(':', 1)
                    masked_url = f"{protocol}://***:***@{host_part}"
                else:
                    masked_url = f"{protocol}://***@{host_part}"
            else:
                masked_url = database_url
        else:
            masked_url = database_url
    except Exception:
        # Fallback to simple masking if parsing fails
        masked_url = database_url.replace('://', '://***:***@') if '@' in database_url else database_url
    print(f"SETTINGS.PY DEBUG: Before fallback, DATABASE_URL is: {masked_url}", flush=True)
else:
    print("SETTINGS.PY DEBUG: Before fallback, DATABASE_URL is: NOT_SET", flush=True)

database_host = env('DJANGO_DATABASE_HOST', default=None)
if database_host:
    print(f"SETTINGS.PY DEBUG: Before fallback, DJANGO_DATABASE_HOST is: {database_host}", flush=True)
else:
    print("SETTINGS.PY DEBUG: Before fallback, DJANGO_DATABASE_HOST is: NOT_SET", flush=True)

if not env("DATABASE_URL", default=None):
    print("SETTINGS.PY DEBUG: DATABASE_URL is NOT SET or empty, entering fallback logic.", flush=True)
    db_user = env("DJANGO_DATABASE_USER", default="postgres")
    db_password = env("DJANGO_DATABASE_PASSWORD", default="postgres")
    db_host = env("DJANGO_DATABASE_HOST", default="localhost")
    db_port = env("DJANGO_DATABASE_PORT", default="5432")
    db_name = env("DJANGO_DATABASE_NAME", default="postgres")
    constructed_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    env.ENVIRON["DATABASE_URL"] = constructed_url
else:
    print("SETTINGS.PY DEBUG: DATABASE_URL IS SET, skipping fallback logic.", flush=True)


class Base(Configuration):
    """Base configuration that all other configurations inherit from."""

    # Branding for emails
    EMAIL_BRAND_NAME = env("EMAIL_BRAND_NAME", default="Ben Heath SaaS")
    EMAIL_LOGO_IMG = env("EMAIL_LOGO_IMG", default="https://benheath.com/static/logo.png")
    EMAIL_FROM = env("EMAIL_FROM", default="noreply@benheath.com")

    NANGO_SECRET_KEY = env("NANGO_SECRET_KEY", default="nango_secret_key")
    NANGO_HOST = env("NANGO_HOST", default="https://nango.opie.sh")

    # Quick-start development settings - unsuitable for production
    # See https://docs.djangoproject.com/en/stable/howto/deployment/checklist/

    # SECURITY WARNING: keep the secret key used in production secret!
    SECRET_KEY = values.Value(env("SECRET_KEY", default="django-insecure-crEWlPWyA2NZ7FqdW4oLRoszLrFw7PthKJI0Qj8c"))

    # SECURITY WARNING: don"t run with debug turned on in production!
    DEBUG = values.BooleanValue(env.bool("DEBUG", default=True))
    ENABLE_DEBUG_TOOLBAR = values.BooleanValue(
        env.bool("ENABLE_DEBUG_TOOLBAR", default=False) and "test" not in sys.argv
    )

    # Note: It is not recommended to set ALLOWED_HOSTS to "*" in production
    ALLOWED_HOSTS = values.ListValue(env.list("ALLOWED_HOSTS", default=["*"]))

    # API Version (Docs)
    API_VERSION = "v1.0"

    # Application definition

    DJANGO_APPS = [
        "django.contrib.admin",
        "django.contrib.admindocs",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.sitemaps",
        "django.contrib.messages",
        "django.contrib.staticfiles",
        "django.contrib.sites",
        "django.forms",
    ]

    # Put your third-party apps here
    THIRD_PARTY_APPS = [
        "allauth",  # allauth account/registration management
        "allauth.account",
        "allauth.socialaccount",
        "allauth.socialaccount.providers.google",
        "allauth.headless",
        "channels",
        "allauth.mfa",
        "rest_framework",
        "rest_framework.authtoken",
        "rest_framework_simplejwt",
        "corsheaders",
        "dj_rest_auth",
        "dj_rest_auth.registration",
        "drf_spectacular",
        "rest_framework_api_key",
        "celery_progress",
        "hijack",  # "login as" functionality
        "hijack.contrib.admin",  # hijack buttons in the admin
        "djstripe",  # stripe integration
        "whitenoise.runserver_nostatic",  # whitenoise runserver
        "waffle",
        "health_check",
        "health_check.db",
        "health_check.contrib.celery",
        "health_check.contrib.redis",
        "django_celery_beat",
        "storages",
        "django_extensions",
        # "django_cryptography",
    ]

    WAGTAIL_APPS = [
        "wagtail.contrib.forms",
        "wagtail.contrib.redirects",
        "wagtail.contrib.simple_translation",
        "wagtail.embeds",
        "wagtail.sites",
        "wagtail.users",
        "wagtail.snippets",
        "wagtail.documents",
        "wagtail.images",
        "wagtail.locales",
        "wagtail.search",
        "wagtail.admin",
        "wagtail",
        "modelcluster",
        "taggit",
    ]

    # Put your project-specific apps here
    PROJECT_APPS = [
        # "apps.content"
        "apps.subscriptions.apps.SubscriptionConfig",
        "apps.users.apps.UserConfig",
        "apps.dashboard.apps.DashboardConfig",
        "apps.api.apps.APIConfig",
        "apps.web",
        "apps.teams.apps.TeamConfig",
        "apps.teams_example.apps.TeamsExampleConfig",
        # "apps.ai_images",
        # "apps.chat",
        "apps.group_chat",
        "apps.reggie",
        "apps.slack_integration",
        "apps.app_integrations",
        "apps.docs",
    ]

    INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + PROJECT_APPS + WAGTAIL_APPS

    if DEBUG and "daphne" not in INSTALLED_APPS:
        # in debug mode, add daphne to the beginning of INSTALLED_APPS to enable async support
        INSTALLED_APPS.insert(0, "daphne")

    MIDDLEWARE = [
        "corsheaders.middleware.CorsMiddleware",
        "django.middleware.security.SecurityMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.locale.LocaleMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "allauth.account.middleware.AccountMiddleware",
        "apps.teams.middleware.TeamsMiddleware",
        "apps.web.middleware.locale.UserLocaleMiddleware",
        "apps.web.middleware.locale.UserTimezoneMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
        "wagtail.contrib.redirects.middleware.RedirectMiddleware",
        "hijack.middleware.HijackUserMiddleware",
        "waffle.middleware.WaffleMiddleware",
    ]

    if ENABLE_DEBUG_TOOLBAR:
        MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
        INSTALLED_APPS.append("debug_toolbar")
        INTERNAL_IPS = ["127.0.0.1"]

    ROOT_URLCONF = "bh_reggie.urls"

    # used to disable the cache in dev, but turn it on in production.
    # more here: https://nickjanetakis.com/blog/django-4-1-html-templates-are-cached-by-default-with-debug-true
    _DEFAULT_LOADERS = [
        "django.template.loaders.filesystem.Loader",
        "django.template.loaders.app_directories.Loader",
    ]

    _CACHED_LOADERS = [("django.template.loaders.cached.Loader", _DEFAULT_LOADERS)]

    TEMPLATES = [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [
                BASE_DIR / "templates",
            ],
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.debug",
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                    "apps.web.context_processors.project_meta",
                    "apps.teams.context_processors.team",
                    "apps.teams.context_processors.user_teams",
                    # this line can be removed if not using google analytics
                    "apps.web.context_processors.google_analytics_id",
                ],
                "loaders": _DEFAULT_LOADERS if DEBUG else _CACHED_LOADERS,
            },
        },
    ]

    WSGI_APPLICATION = "bh_reggie.wsgi.application"

    FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

    # Database
    # https://docs.djangoproject.com/en/stable/ref/settings/#databases

    DATABASE_URL = values.Value(env("DATABASE_URL", default=None))

    @property
    def DATABASES(self):
        if "DATABASE_URL" in env:
            default_db = env.db()
        else:
            default_db = {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": env("DJANGO_DATABASE_NAME", default="bh_reggie"),
                "USER": env("DJANGO_DATABASE_USER", default="ai"),
                "PASSWORD": env("DJANGO_DATABASE_PASSWORD", default="ai"),
                "HOST": env("DJANGO_DATABASE_HOST", default="localhost"),
                "PORT": env("DJANGO_DATABASE_PORT", default="5532"),
            }

        # Inject test database override into the default config
        default_db["TEST"] = {
            "NAME": env("TEST_DATABASE_NAME", default="test_ai_dev"),
        }

        return {"default": default_db}

    # Redis cache (shared across environments)
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": env("REDIS_CACHE_URL", default="redis://localhost:6379/2"),
            "TIMEOUT": None,  # Use per-view TTLs or override per call
        }
    }

    # DATABASE_AI_URL = env("DATABASE_AI_URL", default=env("DATABASE_URL"))

    # Auth and Login

    # Django recommends overriding the user model even if you don"t think you need to because it makes
    # future changes much easier.
    AUTH_USER_MODEL = "users.CustomUser"
    LOGIN_URL = "account_login"
    LOGIN_REDIRECT_URL = "/"

    # SimpleJWT configuration – extend token lifetimes
    SIMPLE_JWT = {
        # 24-hour access tokens
        "ACCESS_TOKEN_LIFETIME": timedelta(hours=24),
        # 30-day refresh tokens
        "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
        "ROTATE_REFRESH_TOKENS": True,
        "BLACKLIST_AFTER_ROTATION": True,
        "UPDATE_LAST_LOGIN": True,
        "SIGNING_KEY": env("SIMPLE_JWT_SIGNING_KEY", default="<a comlex signing key>"),
        "ALGORITHM": "HS256",
    }

    # Session configuration
    SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 days
    SESSION_EXPIRE_AT_BROWSER_CLOSE = False
    SESSION_SAVE_EVERY_REQUEST = True
    SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = "bh_reggie_sessionid"
    # Session cookie domain - set to None for localhost development
    SESSION_COOKIE_DOMAIN = env("SESSION_COOKIE_DOMAIN", default=None)
    SESSION_COOKIE_PATH = "/"

    # Password validation
    # https://docs.djangoproject.com/en/stable/ref/settings/#auth-password-validators

    AUTH_PASSWORD_VALIDATORS = [
        {
            "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        },
        {
            "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        },
        {
            "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
        },
        {
            "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
        },
    ]

    # Invitation settings
    INVITATION_VALIDITY_DURATION = 7 * 24 * 60 * 60  # 7 days in seconds

    # Allauth setup
    ACCOUNT_ADAPTER = "apps.teams.adapter.AcceptInvitationAdapter"
    HEADLESS_ADAPTER = "apps.users.adapter.CustomHeadlessAdapter"
    # Ensure allauth headless is properly configured
    ALLAUTH_HEADLESS_ENABLED = True
    ACCOUNT_LOGIN_METHODS = {"email"}
    ACCOUNT_SIGNUP_FIELDS = {
        "email": {"required": True},
        "password1": {"required": True},
        "password2": {"required": True},
    }
    ACCOUNT_USER_MODEL_USERNAME_FIELD = "username"

    ACCOUNT_EMAIL_SUBJECT_PREFIX = ""
    ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False  # don't send "forgot password" emails to unknown accounts
    ACCOUNT_CONFIRM_EMAIL_ON_GET = True
    ACCOUNT_UNIQUE_EMAIL = True
    ACCOUNT_SESSION_REMEMBER = True
    ACCOUNT_LOGOUT_ON_GET = True
    ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
    ACCOUNT_LOGIN_BY_CODE_ENABLED = True

    ACCOUNT_FORMS = {
        "signup": "apps.teams.forms.TeamSignupForm",
    }
    SOCIALACCOUNT_FORMS = {
        "signup": "apps.users.forms.CustomSocialSignupForm",
    }

    # User signup configuration: change to "mandatory" to require users to confirm email before signing in.
    # or "optional" to send confirmation emails but not require them
    ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", default="none")

    AUTHENTICATION_BACKENDS = (
        "django.contrib.auth.backends.ModelBackend",  # Django's default backend
        "allauth.account.auth_backends.AuthenticationBackend",  # AllAuth backend
    )

    # enable social login
    SOCIALACCOUNT_PROVIDERS = {
        "google": {
            "APPS": [
                {
                    "client_id": env("GOOGLE_CLIENT_ID", default=""),
                    "secret": env("GOOGLE_SECRET_ID", default=""),
                    "key": "",
                },
            ],
            "SCOPE": [
                "profile",
                "email",
            ],
            "AUTH_PARAMS": {
                "access_type": "online",
            },
        },
    }

    # For turnstile captchas
    TURNSTILE_KEY = env("TURNSTILE_KEY", default=None)
    TURNSTILE_SECRET = env("TURNSTILE_SECRET", default=None)

    # Internationalization
    # https://docs.djangoproject.com/en/stable/topics/i18n/

    LANGUAGE_CODE = "en-us"
    LANGUAGE_COOKIE_NAME = "bh_reggie_language"
    LANGUAGES = WAGTAIL_CONTENT_LANGUAGES = [
        ("en", gettext_lazy("English")),
        ("fr", gettext_lazy("French")),
    ]
    LOCALE_PATHS = (BASE_DIR / "locale",)

    TIME_ZONE = "UTC"

    USE_I18N = WAGTAIL_I18N_ENABLED = True

    USE_TZ = True

    # Static files (CSS, JavaScript, Images)
    # https://docs.djangoproject.com/en/stable/howto/static-files/

    STATIC_ROOT = BASE_DIR / "static_root"
    STATIC_URL = "/static/"

    STATICFILES_DIRS = [
        BASE_DIR / "static",
    ]

    # CONFIGURE STORAGE SETTINGS
    # File/media storage configuration
    USE_S3_MEDIA = env.bool("USE_S3_MEDIA", default=False)
    USE_GCS_MEDIA = env.bool("USE_GCS_MEDIA", default=False)

    # === Default: Local File Storage ===
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"
    STATIC_URL = "/static/"
    STATIC_ROOT = BASE_DIR / "staticfiles"

    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
        },
    }

    # === AWS S3 Media Storage ===
    if USE_S3_MEDIA:
        AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
        AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
        AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="bh-reggie-media")
        AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"
        PUBLIC_MEDIA_LOCATION = "media"
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{PUBLIC_MEDIA_LOCATION}/"

        STORAGES["default"] = {
            "BACKEND": "apps.web.storage_backends.PublicMediaStorage",
        }

    # === Google Cloud Storage ===
    elif USE_GCS_MEDIA:
        GCS_BUCKET_NAME = env("GCS_BUCKET_NAME", default="bh-reggie-media")
        GCS_STATIC_BUCKET_NAME = env("GCS_STATIC_BUCKET_NAME")
        GCS_PROJECT_ID = env("GCS_PROJECT_ID")
        GCS_SERVICE_ACCOUNT_FILE = env("GCS_SERVICE_ACCOUNT_FILE")

        from google.oauth2 import service_account

        GCS_CREDENTIALS = service_account.Credentials.from_service_account_file(
            os.path.join(BASE_DIR, GCS_SERVICE_ACCOUNT_FILE)
        )

        MEDIA_URL = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/"
        STATIC_URL = f"https://storage.googleapis.com/{GCS_STATIC_BUCKET_NAME}/"

        STORAGES = {
            "default": {
                "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
                "OPTIONS": {
                    "bucket_name": GCS_BUCKET_NAME,
                    "credentials": GCS_CREDENTIALS,
                    "location": "",
                },
            },
            "staticfiles": {
                "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
                "OPTIONS": {
                    "bucket_name": GCS_STATIC_BUCKET_NAME,
                    "credentials": GCS_CREDENTIALS,
                    "location": "",
                },
            },
        }

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(BASE_DIR, GCS_SERVICE_ACCOUNT_FILE)

    else:
        # Local development fallback
        MEDIA_URL = "/media/"
        MEDIA_ROOT = BASE_DIR / "media"
        STATIC_URL = "/static/"
        STATIC_ROOT = BASE_DIR / "staticfiles"

    # Default primary key field type
    # https://docs.djangoproject.com/en/stable/ref/settings/#default-auto-field

    # future versions of Django will use BigAutoField as the default, but it can result in unwanted library
    # migration files being generated, so we stick with AutoField for now.
    # change this to BigAutoField if you"re sure you want to use it and aren"t worried about migrations.
    DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

    # Removes deprecation warning for future compatibility.
    # see https://adamj.eu/tech/2023/12/07/django-fix-urlfield-assume-scheme-warnings/ for details.
    FORMS_URLFIELD_ASSUME_HTTPS = True

    # Email setup

    # default email used by your server
    SERVER_EMAIL = env("SERVER_EMAIL", default="noreply@localhost:8000")
    DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="hello@benheath.com.au")

    # The default value will print emails to the console, but you can change that here
    # and in your environment.
    EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")

    # Most production backends will require further customization. The below example uses Mailgun.
    ANYMAIL = {
        "MAILGUN_API_KEY": env("MAILGUN_API_KEY", default=None),
        "MAILGUN_SENDER_DOMAIN": env("MAILGUN_SENDER_DOMAIN", default=None),
    }

    # use in production
    # see https://github.com/anymail/django-anymail for more details/examples
    # EMAIL_BACKEND = "anymail.backends.mailgun.EmailBackend"

    EMAIL_SUBJECT_PREFIX = "[Ben Heath SaaS] "

    # Marketing email configuration

    # set these values if you want to subscribe people to a mailing list when they sign up.
    MAILCHIMP_API_KEY = env("MAILCHIMP_API_KEY", default="")
    MAILCHIMP_LIST_ID = env("MAILCHIMP_LIST_ID", default="")

    # Django sites

    SITE_ID = 1

    # DRF config
    API_USERS_LIST_LIMIT = 20
    REST_FRAMEWORK = {
        "DEFAULT_THROTTLE_RATES": {
            "user_list_burst": "3/minute",
            "user_list_sustained": "3/minute",
        },
        "DEFAULT_AUTHENTICATION_CLASSES": (
            "rest_framework_simplejwt.authentication.JWTAuthentication",
            "rest_framework.authentication.SessionAuthentication",
        ),
        "DEFAULT_PERMISSION_CLASSES": ("apps.api.permissions.IsAuthenticatedOrHasUserAPIKey",),
        "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
        "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
        "PAGE_SIZE": 10,
        "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
        "DEFAULT_VERSION": "v1",
        "ALLOWED_VERSIONS": ["v1"],
        "VERSION_PARAM": "version",
    }

    REST_AUTH = {
        "USE_JWT": True,
        "JWT_AUTH_HTTPONLY": False,
        "USER_DETAILS_SERIALIZER": "apps.users.serializers.CustomUserSerializer",
    }

    REST_AUTH_REGISTER_SERIALIZERS = {
        "REGISTER_SERIALIZER": "apps.authentication.serializers.CustomRegisterSerializer",
    }

    CORS_ALLOWED_ORIGINS = env.list(
        "CORS_ALLOWED_ORIGINS",
        default=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
    )
    # print(f"DEBUG: CORS_ALLOWED_ORIGINS = {CORS_ALLOWED_ORIGINS}")
    CORS_ALLOW_CREDENTIALS = True
    CORS_ALLOW_METHODS = [
        "DELETE",
        "GET",
        "OPTIONS",
        "PATCH",
        "POST",
        "PUT",
    ]
    CORS_ALLOW_HEADERS = [
        "accept",
        "accept-encoding",
        "authorization",
        "content-type",
        "dnt",
        "origin",
        "user-agent",
        "x-csrftoken",
        "x-requested-with",
        "content-disposition",
        "content-length",
        "credentials",
    ]
    CORS_EXPOSE_HEADERS = [
        "content-disposition",
        "content-length",
    ]
    # Note: CORS_ALLOW_ALL_ORIGINS and CORS_ORIGIN_ALLOW_ALL are incompatible with CORS_ALLOW_CREDENTIALS
    # Use CORS_ALLOWED_ORIGINS instead for development
    CORS_ORIGIN_ALLOW_ALL = False  # Disabled to allow credentials
    CORS_ALLOW_ALL_ORIGINS = False  # Disabled to allow credentials

    # Spectacular settings
    SPECTACULAR_SETTINGS = {
        "TITLE": "Reggie API",
        "DESCRIPTION": "API documentation for Reggie SaaS application",
        "VERSION": "1.0.0",
        "SERVE_INCLUDE_SCHEMA": False,
        "SWAGGER_UI_SETTINGS": {
            "deepLinking": True,
            "persistAuthorization": True,
            "displayOperationId": True,
        },
        "COMPONENT_SPLIT_REQUEST": True,
        "TAGS": [
            {"name": "auth", "description": "Authentication operations"},
            {"name": "users", "description": "User management operations"},
            {"name": "teams", "description": "Team management operations"},
            {"name": "files", "description": "File management operations"},
            {"name": "projects", "description": "Project management operations"},
            {"name": "integrations", "description": "Third-party integrations"},
        ],
        "PREPROCESSING_HOOKS": ["apps.api.schema.filter_schema_apis"],
    }

    # Redis, cache, and/or Celery setup
    if "REDIS_URL" in env:
        REDIS_URL = env("REDIS_URL")
    elif "REDIS_TLS_URL" in env:
        REDIS_URL = env("REDIS_TLS_URL")
    else:
        REDIS_HOST = env("REDIS_HOST", default="localhost")
        REDIS_PORT = env("REDIS_PORT", default="6379")
        REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

    if REDIS_URL.startswith("rediss"):
        REDIS_URL = f"{REDIS_URL}?ssl_cert_reqs=none"

    DUMMY_CACHE = {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
    REDIS_CACHE = {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
    CACHES = {
        "default": DUMMY_CACHE if DEBUG else REDIS_CACHE,
    }

    CELERY_BROKER_URL = CELERY_RESULT_BACKEND = REDIS_URL
    CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
    # Debug info without exposing sensitive data
    # print(f"CELERY_BROKER_URL configured: {REDIS_URL.split('@')[-1] if '@' in REDIS_URL else 'localhost'}")
    # print(f"CELERY_RESULT_BACKEND configured: {REDIS_URL.split('@')[-1] if '@' in REDIS_URL else 'localhost'}")
    # print("CELERY_BEAT_SCHEDULER configured")
    # see apps/subscriptions/migrations/0001_celery_tasks.py for scheduled tasks

    # Channels / Daphne setup

    ASGI_APPLICATION = "bh_reggie.asgi.application"
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
            },
        },
    }

    # Health Checks
    # A list of tokens that can be used to access the health check endpoint
    HEALTH_CHECK_TOKENS = env.list("HEALTH_CHECK_TOKENS", default="")

    # Wagtail config

    WAGTAIL_SITE_NAME = "Ben Heath SaaS Content"
    WAGTAILADMIN_BASE_URL = "http://localhost:8000"

    # Waffle config

    WAFFLE_FLAG_MODEL = "teams.Flag"

    # Pegasus config

    # replace any values below with specifics for your project
    PROJECT_METADATA = {
        "NAME": gettext_lazy("Ben Heath SaaS"),
        "URL": "http://localhost:8000",
        "DESCRIPTION": gettext_lazy("BH Blockchain Analytics Platform"),
        "IMAGE": "https://upload.wikimedia.org/wikipedia/commons/2/20/PEO-pegasus_black.svg",
        "KEYWORDS": "SaaS, django",
        "CONTACT_EMAIL": "hello@benheath.com.au",
    }

    # set this to True in production to have URLs generated with https instead of http
    USE_HTTPS_IN_ABSOLUTE_URLS = env.bool("USE_HTTPS_IN_ABSOLUTE_URLS", default=False)

    ADMINS = [("Ben", "hello@benheath.com.au")]

    # Add your google analytics ID to the environment to connect to Google Analytics
    GOOGLE_ANALYTICS_ID = env("GOOGLE_ANALYTICS_ID", default="")

    # these daisyui themes are used to set the dark and light themes for the site
    # they must be valid themes included in your tailwind.config.js file.
    # more here: https://daisyui.com/docs/themes/
    LIGHT_THEME = "light"
    DARK_THEME = "dark"

    # Stripe config
    # modeled to be the same as https://github.com/dj-stripe/dj-stripe
    # Note: don"t edit these values here - edit them in your .env file or environment variables!
    # The defaults are provided to prevent crashes if your keys don"t match the expected format.
    STRIPE_LIVE_PUBLIC_KEY = env("STRIPE_LIVE_PUBLIC_KEY", default="pk_live_***")
    STRIPE_LIVE_SECRET_KEY = env("STRIPE_LIVE_SECRET_KEY", default="sk_live_***")
    STRIPE_TEST_PUBLIC_KEY = env("STRIPE_TEST_PUBLIC_KEY", default="pk_test_***")
    STRIPE_TEST_SECRET_KEY = env("STRIPE_TEST_SECRET_KEY", default="sk_test_***")
    # Change to True in production
    STRIPE_LIVE_MODE = env.bool("STRIPE_LIVE_MODE", False)
    STRIPE_PRICING_TABLE_ID = env("STRIPE_PRICING_TABLE_ID", default="")

    # djstripe settings
    # Get it from the section in the Stripe dashboard where you added the webhook endpoint
    # or from the stripe CLI when testing
    DJSTRIPE_WEBHOOK_SECRET = env("DJSTRIPE_WEBHOOK_SECRET", default="whsec_***")

    DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"  # change to "djstripe_id" if not a new installation
    DJSTRIPE_SUBSCRIBER_MODEL = "teams.Team"

    def get_subscriber_from_request(request):
        """Get the subscriber (team) from the request."""
        if hasattr(request, "team"):
            return request.team
        return None

    DJSTRIPE_SUBSCRIBER_MODEL_REQUEST_CALLBACK = get_subscriber_from_request

    SILENCED_SYSTEM_CHECKS = [
        "djstripe.I002",  # Pegasus uses the same settings as dj-stripe for keys, so don't complain they are here
    ]

    if "test" in sys.argv:
        # Silence unnecessary warnings in tests
        SILENCED_SYSTEM_CHECKS.append("djstripe.I002")

    # list of support model providers (LLM Providers)
    MODEL_PROVIDERS = [
        ("openai", "OpenAI"),
        ("google", "Google"),
        ("anthropic", "Anthropic"),
        ("groq", "Groq"),
    ]

    MODEL_PROVIDER_CLASSES = {
        "openai": "agno.models.openai.OpenAIChat",
        "google": "agno.models.google.Gemini",
        "anthropic": "agno.models.anthropic.Claude",
        "groq": "agno.models.groq.Groq",
    }

    # AI Image Setup
    AI_IMAGES_STABILITY_AI_API_KEY = env("AI_IMAGES_STABILITY_AI_API_KEY", default="")
    AI_IMAGES_OPENAI_API_KEY = env("AI_IMAGES_OPENAI_API_KEY", default="")

    # AI Chat Setup
    AI_CHAT_OPENAI_API_KEY = env("AI_CHAT_OPENAI_API_KEY", default="")
    AI_CHAT_OPENAI_MODEL = env("AI_CHAT_OPENAI_MODEL", default="gpt-4o")

    # === Slack Tokens ===
    SLACK_BOT_TOKEN = env("SLACK_BOT_TOKEN", default="")

    # === Slack OAuth Credentials ===
    SLACK_SIGNING_SECRET = env("SLACK_SIGNING_SECRET", default="signing")
    SLACK_CLIENT_ID = env("SLACK_CLIENT_ID", default="client-id")
    SLACK_CLIENT_SECRET = env("SLACK_CLIENT_SECRET", default="client-secret")
    SLACK_SCOPES = env("SLACK_SCOPES", default="app_mentions:read,chat:write")
    SLACK_BOT_USER_ID = env("SLACK_BOT_USER_ID", default="bot-user-id")
    SLACK_REDIRECT_URI = env("SLACK_REDIRECT_URI", default="https://yourdomain.com/slack/oauth/callback/")

    # === OpenAI ===
    OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
    GOOGLE_API_KEY = env("GOOGLE_API_KEY", default="")

    # === Jira Integration ===
    JIRA_SERVER = env("JIRA_SERVER_URL", default="")
    JIRA_USERNAME = env("JIRA_USERNAME", default="")
    JIRA_PASSWORD = env("JIRA_PASSWORD", default="")
    JIRA_TOKEN = env("JIRA_TOKEN", default="")

    # === Google OAUTH Integration ===
    GOOGLE_CLIENT_ID = "776892553125-o3lp4vns1mdd5mv3b6nnm8brf5gde83u.apps.googleusercontent.com"
    GOOGLE_CLIENT_SECRET = "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"
    GOOGLE_REDIRECT_URI = "http://localhost:8000/integrations/gdrive/oauth/callback/"

    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": '[{asctime}] {levelname} "{name}" {message}',
                "style": "{",
                "datefmt": "%d/%b/%Y %H:%M:%S",  # match Django server time format
            },
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        },
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": env("DJANGO_LOG_LEVEL", default="INFO"),
            },
            "bh_reggie": {
                "handlers": ["console"],
                "level": env("BH_REGGIE_LOG_LEVEL", default="INFO"),
            },
            # Add authentication debugging
            "django.contrib.auth": {
                "handlers": ["console"],
                "level": "DEBUG",
                "propagate": False,
            },
            "django.contrib.sessions": {
                "handlers": ["console"],
                "level": "DEBUG",
                "propagate": False,
            },
            "rest_framework_simplejwt": {
                "handlers": ["console"],
                "level": "DEBUG",
                "propagate": False,
            },
            "mozilla_django_oidc": {
                "handlers": ["console"],
                "level": "DEBUG",
                "propagate": False,
            },
            "apps.reggie": {  # <--- Added logger for your app
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }

    # Add file logging only in development
    if DEBUG:
        LOGGING["handlers"]["file"] = {
            "class": "logging.FileHandler",
            "filename": str(BASE_DIR / "logs" / "bh_reggie.log"),
            "formatter": "verbose",
        }
        LOGGING["loggers"]["django"]["handlers"].append("file")
        LOGGING["loggers"]["bh_reggie"]["handlers"].append("file")

    # === Agno Agent settings ===

    # Agent memory table
    AGENT_MEMORY_TABLE = env("AGENT_MEMORY_TABLE", default="reggie_memory")
    AGENT_STORAGE_TABLE = env("AGENT_STORAGE_TABLE", default="reggie_storage_sessions")
    AGENT_SCHEMA = env("AGENT_SCHEMA", default="ai")

    # === Collaboration Settings ===
    COLLABORATION_API_URL = env("COLLABORATION_API_URL", default="http://y-provider:4444/collaboration/api/")
    COLLABORATION_BACKEND_BASE_URL = env("COLLABORATION_BACKEND_BASE_URL", default="http://app-dev:8000")
    COLLABORATION_SERVER_ORIGIN = env("COLLABORATION_SERVER_ORIGIN", default="http://localhost:3000")
    COLLABORATION_SERVER_SECRET = env("COLLABORATION_SERVER_SECRET", default="my-secret")
    COLLABORATION_WS_URL = env("COLLABORATION_WS_URL", default="ws://localhost:4444/collaboration/ws/")
    
    # Document trashbin retention policy (in days)
    TRASHBIN_CUTOFF_DAYS = env.int("TRASHBIN_CUTOFF_DAYS", default=30)

    # === LlamaIndex Settings ===
    LLAMAINDEX_INGESTION_URL = env("CLOUD_RUN_BASE_URL", default="http://127.0.0.1:8080")

    # Google Cloud Storage settings
    GS_FILE_OVERWRITE = False  # Prevent accidental file overwrites

    # Cache timeout for the footer view in seconds
    FRONTEND_FOOTER_VIEW_CACHE_TIMEOUT = 3600

    # OIDC Settings
    OIDC_RP_CLIENT_ID = env("OIDC_RP_CLIENT_ID", default="")
    OIDC_RP_CLIENT_SECRET = env("OIDC_RP_CLIENT_SECRET", default="")
    OIDC_RP_SIGN_ALGO = "RS256"
    OIDC_RP_SCOPES = "openid email profile"
    OIDC_RP_IDP_SIGN_KEY = env("OIDC_RP_IDP_SIGN_KEY", default="")

    # OIDC Provider Settings
    OIDC_OP_AUTHORIZATION_ENDPOINT = env(
        "OIDC_OP_AUTHORIZATION_ENDPOINT", default="http://oidc.endpoint.test/authorize"
    )
    OIDC_OP_TOKEN_ENDPOINT = env("OIDC_OP_TOKEN_ENDPOINT", default="http://oidc.endpoint.test/token")
    OIDC_OP_USER_ENDPOINT = env("OIDC_OP_USER_ENDPOINT", default="http://oidc.endpoint.test/userinfo")
    OIDC_OP_JWKS_ENDPOINT = env("OIDC_OP_JWKS_ENDPOINT", default="http://oidc.endpoint.test/jwks")
    OIDC_OP_LOGOUT_ENDPOINT = env("OIDC_OP_LOGOUT_ENDPOINT", default="http://oidc.endpoint.test/logout")

    # OIDC Login Settings
    OIDC_RP_CLIENT_AUTHN_METHOD = "client_secret_post"
    OIDC_RP_REDIRECT_URI = env("OIDC_RP_REDIRECT_URI", default="http://localhost:8000/api/auth/oidc/callback/")
    OIDC_RP_SCOPES = "openid email profile"
    OIDC_RP_USE_NONCE = True
    OIDC_RP_USE_PKCE = True

    # OIDC Authentication Settings
    OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION = False
    OIDC_ALLOW_DUPLICATE_EMAILS = False
    USER_OIDC_ESSENTIAL_CLAIMS = ["email", "sub"]
    USER_OIDC_FIELDS_TO_FULLNAME = ["first_name", "last_name"]
    USER_OIDC_FIELD_TO_SHORTNAME = "first_name"

    # Impress AI service
    GCS_DOCS_BUCKET_NAME = env("GCS_DOCS_BUCKET_NAME", default="bh-reggie-docs")
    AI_FEATURE_ENABLED = env.bool("AI_FEATURE_ENABLED", default=False)
    AI_API_KEY = env("AI_API_KEY", default=None)
    AI_BASE_URL = env("AI_BASE_URL", default=None)
    AI_MODEL = env("AI_MODEL", default=None)
    AI_ALLOW_REACH_FROM = env("AI_ALLOW_REACH_FROM", default="authenticated")
    AI_DOCUMENT_RATE_THROTTLE_RATES = {
        "minute": 5,
        "hour": 100,
        "day": 500,
    }
    AI_USER_RATE_THROTTLE_RATES = {
        "minute": 3,
        "hour": 50,
        "day": 200,
    }

    # Y provider microservice
    Y_PROVIDER_API_KEY = env("Y_PROVIDER_API_KEY", default=None)
    Y_PROVIDER_API_BASE_URL = env("Y_PROVIDER_API_BASE_URL", default=None)

    # Conversion endpoint
    CONVERSION_API_ENDPOINT = env("CONVERSION_API_ENDPOINT", default="convert-markdown")
    CONVERSION_API_CONTENT_FIELD = env("CONVERSION_API_CONTENT_FIELD", default="content")
    CONVERSION_API_TIMEOUT = env("CONVERSION_API_TIMEOUT", default=30)
    CONVERSION_API_SECURE = env.bool("CONVERSION_API_SECURE", default=False)

    # === Mobile App Security Settings ===
    MOBILE_APP_IDS = env.list("MOBILE_APP_IDS", default=["com.benheath.reggie.ios", "com.benheath.reggie.android"])
    MOBILE_APP_MIN_VERSION = env("MOBILE_APP_MIN_VERSION", default="1.0.0")

    # === JWT Security Settings ===
    JWT_AUTH_COOKIE = env("JWT_AUTH_COOKIE", default="access_token")
    JWT_AUTH_REFRESH_COOKIE = env("JWT_AUTH_REFRESH_COOKIE", default="refresh_token")
    JWT_AUTH_SECURE = env.bool("JWT_AUTH_SECURE", default=True)
    JWT_AUTH_SAMESITE = env("JWT_AUTH_SAMESITE", default="Lax")


class Development(Base):
    """Development environment settings."""

    DEBUG = True
    ALLOWED_HOSTS = ["*"]
    # Remove CORS_ALLOW_ALL_ORIGINS since it's incompatible with CORS_ALLOW_CREDENTIALS
    # The Base class already has CORS_ALLOWED_ORIGINS set correctly
    CSRF_TRUSTED_ORIGINS = [
        "http://localhost:8072",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5174",
        "https://app.opie.sh",
        "https://api.opie.sh",
    ]

    # CSRF cookie settings for cross-domain access
    CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)
    CSRF_COOKIE_SAMESITE = env("CSRF_COOKIE_SAMESITE", default="Lax")
    CSRF_COOKIE_HTTPONLY = False  # Must be False for JavaScript access
    CSRF_COOKIE_DOMAIN = env("CSRF_COOKIE_DOMAIN", default=None)

    # print("ALLOWED_HOSTS", ALLOWED_HOSTS)
    # print("CSRF_TRUSTED_ORIGINS", CSRF_TRUSTED_ORIGINS)
    # Use local static and media storage for development
    STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
    DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
    STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
    MEDIA_ROOT = os.path.join(BASE_DIR, "media")
    STATIC_URL = "/static/"

    def __init__(self):
        super().__init__()
        if self.DEBUG and "daphne" not in self.INSTALLED_APPS:
            self.INSTALLED_APPS.insert(0, "daphne")
        if self.ENABLE_DEBUG_TOOLBAR:
            self.MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
            self.INSTALLED_APPS.append("debug_toolbar")
            self.INTERNAL_IPS = ["127.0.0.1"]


class Test(Base):
    """Test environment settings."""

    DEBUG = True
    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]


class Production(Base):
    """Production environment settings."""

    DEBUG = False
    ALLOWED_HOSTS = values.ListValue(["*"])
    CSRF_TRUSTED_ORIGINS = values.ListValue(["https://app.opie.sh", "https://api.opie.sh"])
    # print("ALLOWED_HOSTS", ALLOWED_HOSTS)
    # print("CSRF_TRUSTED_ORIGINS", CSRF_TRUSTED_ORIGINS)
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 60
    SECURE_HSTS_PRELOAD = True
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [
        "^__lbheartbeat__",
        "^__heartbeat__",
    ]
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_REFERRER_POLICY = "same-origin"


class Staging(Production):
    """Staging environment settings."""

    pass


class PreProduction(Production):
    """Pre-production environment settings."""

    pass


class Demo(Production):
    """Demonstration environment settings."""

    pass
