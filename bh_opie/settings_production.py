# flake8: noqa: F405
import os
from .settings import *  # noqa F401

# Initialize Sentry after GCP secrets are loaded
if env("DJANGO_CONFIGURATION", default="Development") == "Production":
    import sentry_sdk
    from sentry_sdk.integrations.asgi import AsgiIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=env("SENTRY_DSN"),
        integrations=[DjangoIntegration(), AsgiIntegration()],
        send_default_pii=True,
        traces_sample_rate=0.1,
        environment="production",
    )

# Note: it is recommended to use the "DEBUG" environment variable to override this value in your main settings.py file.
# A future release may remove it from here.
DEBUG = False

# fix ssl mixed content issues
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Django security checklist settings.
# More details here: https://docs.djangoproject.com/en/stable/howto/deployment/checklist/
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Cross-domain cookie settings for WebSocket collaboration
SESSION_COOKIE_SAMESITE = env("SESSION_COOKIE_SAMESITE", default="None")
CSRF_COOKIE_SAMESITE = env("CSRF_COOKIE_SAMESITE", default="None")
SESSION_COOKIE_DOMAIN = env("SESSION_COOKIE_DOMAIN", default=".opie.sh")
CSRF_COOKIE_DOMAIN = env("CSRF_COOKIE_DOMAIN", default=".opie.sh")
CSRF_COOKIE_HTTPONLY = False  # Must be False for JavaScript access in WebSocket

# HTTP Strict Transport Security settings
# Without uncommenting the lines below, you will get security warnings when running ./manage.py check --deploy
# https://docs.djangoproject.com/en/stable/ref/middleware/#http-strict-transport-security

# # Increase this number once you're confident everything works https://stackoverflow.com/a/49168623/8207
# SECURE_HSTS_SECONDS = 60
# # Uncomment these two lines if you are sure that you don't host any subdomains over HTTP.
# You will get security warnings if you don't do this.
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True

USE_HTTPS_IN_ABSOLUTE_URLS = True

# Default configuration for ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["https://app.opie.sh", "https://api.opie.sh"])

# Optional Cloud Run configuration override
CLOUDRUN_SERVICE_URL = env("CLOUDRUN_SERVICE_URL", default=None)
if CLOUDRUN_SERVICE_URL:
    from urllib.parse import urlparse

    # Add Cloud Run specific host to allowed hosts
    cloudrun_host = urlparse(CLOUDRUN_SERVICE_URL).netloc
    if cloudrun_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(cloudrun_host)

    # Add Cloud Run URL to trusted origins if not already present
    if CLOUDRUN_SERVICE_URL not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(CLOUDRUN_SERVICE_URL)

print("ALLOWED_HOSTS", ALLOWED_HOSTS)
print("CSRF_TRUSTED_ORIGINS", CSRF_TRUSTED_ORIGINS)
# CORS configuration for cross-domain WebSocket collaboration
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["https://collab.opie.sh", "wss://collab.opie.sh", "https://app.opie.sh", "https://api.opie.sh"],
)
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
    "sec-websocket-protocol",
    "sec-websocket-extensions",
    "sec-websocket-key",
    "sec-websocket-version",
    "credentials",
]
CORS_EXPOSE_HEADERS = [
    "content-disposition",
    "content-length",
]
# Ensure CORS_ALLOW_ALL_ORIGINS is False in production for security
CORS_ORIGIN_ALLOW_ALL = False
CORS_ALLOW_ALL_ORIGINS = False
# Force GCS usage in production
USE_GCS_MEDIA = True

# Debug logging for environment variables from GCP secrets
print(f"SETTINGS.PY PRODUCTION DEBUG: Environment variables check:")
print(f"SETTINGS.PY PRODUCTION DEBUG: GCS_BUCKET_NAME from env: {os.environ.get('GCS_BUCKET_NAME', 'NOT_SET')}")
print(f"SETTINGS.PY PRODUCTION DEBUG: GCS_STATIC_BUCKET_NAME from env: {os.environ.get('GCS_STATIC_BUCKET_NAME', 'NOT_SET')}")
print(f"SETTINGS.PY PRODUCTION DEBUG: GCS_PROJECT_ID from env: {os.environ.get('GCS_PROJECT_ID', 'NOT_SET')}")

# Google django storages config
# Note: Using GCS_ prefix to match the secret variable names
GS_MEDIA_BUCKET_NAME = env("GCS_BUCKET_NAME", default="bh-opie-media")
GS_STATIC_BUCKET_NAME = env("GCS_STATIC_BUCKET_NAME", default="bh-opie-static")
GCS_PROJECT_ID = env("GCS_PROJECT_ID", default="bh-opie")

# Debug logging for GCS configuration
print(f"SETTINGS.PY PRODUCTION DEBUG: USE_GCS_MEDIA = {USE_GCS_MEDIA}")
print(f"SETTINGS.PY PRODUCTION DEBUG: GS_MEDIA_BUCKET_NAME = {GS_MEDIA_BUCKET_NAME}")
print(f"SETTINGS.PY PRODUCTION DEBUG: GS_STATIC_BUCKET_NAME = {GS_STATIC_BUCKET_NAME}")

# Configure GCS with VM service account
print("SETTINGS.PY PRODUCTION DEBUG: Configuring GCS with VM service account...")
try:
    from google.auth import default
    
    # Use VM default service account via metadata service
    GCS_CREDENTIALS, _ = default()
    print("SETTINGS.PY PRODUCTION DEBUG: Successfully loaded VM service account credentials")
    
    # Override the base settings to use GCS with VM service account
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
            "OPTIONS": {
                "bucket_name": GS_MEDIA_BUCKET_NAME,  # Media bucket for file uploads
                "credentials": GCS_CREDENTIALS,
                "location": "",
            },
        },
        "staticfiles": {
            "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
            "OPTIONS": {
                "bucket_name": GS_STATIC_BUCKET_NAME,  # Static bucket for CSS, JS, images
                "credentials": GCS_CREDENTIALS,
                "location": "",
            },
        },
    }
    
    # Set URLs for GCS
    MEDIA_URL = f"https://storage.googleapis.com/{GS_MEDIA_BUCKET_NAME}/"
    STATIC_URL = f"https://storage.googleapis.com/{GS_STATIC_BUCKET_NAME}/"
    
    print(f"SETTINGS.PY PRODUCTION DEBUG: STORAGES configured with media backend for bucket {GS_MEDIA_BUCKET_NAME}")
    print(f"SETTINGS.PY PRODUCTION DEBUG: STORAGES configured with staticfiles backend for bucket {GS_STATIC_BUCKET_NAME}")
    print(f"SETTINGS.PY PRODUCTION DEBUG: MEDIA_URL = {MEDIA_URL}")
    print(f"SETTINGS.PY PRODUCTION DEBUG: STATIC_URL = {STATIC_URL}")
    
except Exception as e_gcs_config:
    print(f"SETTINGS.PY PRODUCTION DEBUG: Error configuring GCS with VM service account: {e_gcs_config}")
    print("SETTINGS.PY PRODUCTION DEBUG: Falling back to base settings configuration")
    # Fall back to base settings - this will use the base settings GCS logic
    pass

# Set STATIC_ROOT and MEDIA_ROOT for Django
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"

# Remove object-level ACLs; use bucket-level permissions only
GS_DEFAULT_ACL = None  # Always None with uniform bucket-level access
GS_FILE_OVERWRITE = False  # Prevent accidental file overwrites

# Production logging configuration - console only for containerized environments
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": '[{asctime}] {levelname} "{name}" {message}',
            "style": "{",
            "datefmt": "%d/%b/%Y %H:%M:%S",
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
        "bh_opie": {
            "handlers": ["console"],
            "level": env("BH_OPIE_LOG_LEVEL", default="INFO"),
        },
        # Add security logging
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
        },
    },
}

# Your email config goes here.
# see https://github.com/anymail/django-anymail for more details / examples
# To use mailgun, uncomment the lines below and make sure your key and domain
# are available in the environment.
# EMAIL_BACKEND = "anymail.backends.mailgun.EmailBackend"

# ANYMAIL = {
#     "MAILGUN_API_KEY": env("MAILGUN_API_KEY", default=None),
#     "MAILGUN_SENDER_DOMAIN": env("MAILGUN_SENDER_DOMAIN", default=None),
# }

ADMINS = [
    ("Your Name", "hello@benheath.com.au"),
]
