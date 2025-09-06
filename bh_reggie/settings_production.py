# flake8: noqa: F405
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

# Google django storages config
GS_MEDIA_BUCKET_NAME = env("GS_MEDIA_BUCKET_NAME", default="bh-reggie-media")
GS_STATIC_BUCKET_NAME = env("GS_STATIC_BUCKET_NAME", default="bh-reggie-static")
GCS_PROJECT_ID = env("GCS_PROJECT_ID", default="bh-crypto")

# Debug logging for GCS configuration
print(f"SETTINGS.PY PRODUCTION DEBUG: USE_GCS_MEDIA = {USE_GCS_MEDIA}")
print(f"SETTINGS.PY PRODUCTION DEBUG: GS_MEDIA_BUCKET_NAME = {GS_MEDIA_BUCKET_NAME}")
print(f"SETTINGS.PY PRODUCTION DEBUG: GS_STATIC_BUCKET_NAME = {GS_STATIC_BUCKET_NAME}")

# Override the base settings to use GCS
# Note: Credentials are automatically available on GCP via metadata service
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
        "OPTIONS": {
            "bucket_name": GS_MEDIA_BUCKET_NAME,  # Media bucket for file uploads
            "location": "",
        },
    },
    "staticfiles": {
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
        "OPTIONS": {
            "bucket_name": GS_STATIC_BUCKET_NAME,  # Static bucket for CSS, JS, images
            "location": "",
        },
    },
}

print(f"SETTINGS.PY PRODUCTION DEBUG: STORAGES configured with media backend for bucket {GS_MEDIA_BUCKET_NAME}")
print(f"SETTINGS.PY PRODUCTION DEBUG: STORAGES configured with staticfiles backend for bucket {GS_STATIC_BUCKET_NAME}")

## === Google Cloud Storage: Separate buckets for static and media ===
# Remove object-level ACLs; use bucket-level permissions only
GS_DEFAULT_ACL = None  # Always None with uniform bucket-level access

# Static files (public) - CSS, JS, images
STATIC_URL = f"https://storage.googleapis.com/{GS_STATIC_BUCKET_NAME}/"
STATIC_ROOT = BASE_DIR / "staticfiles"
print(f"SETTINGS.PY PRODUCTION DEBUG: STATIC_URL set to {STATIC_URL}")

# Media/uploads (private or restricted) - user uploaded files
MEDIA_URL = f"https://storage.googleapis.com/{GS_MEDIA_BUCKET_NAME}/"
MEDIA_ROOT = BASE_DIR / "media"
print(f"SETTINGS.PY PRODUCTION DEBUG: MEDIA_URL set to {MEDIA_URL}")

# Optionally, add these to your .env:
# GS_STATIC_BUCKET_NAME=bh-reggie-static
# GS_MEDIA_BUCKET_NAME=bh-reggie-media

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
        "bh_reggie": {
            "handlers": ["console"],
            "level": env("BH_REGGIE_LOG_LEVEL", default="INFO"),
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
