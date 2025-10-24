#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

HTTP_PORT=${PORT:-8000}
HTTPS_PORT=8443

# Create GCP credentials file from base64-encoded service account key if provided
if [ -n "$GCP_SA_KEY_BASE64" ]; then
    echo "Creating GCP credentials file from base64-encoded service account key..."
    echo "$GCP_SA_KEY_BASE64" | base64 -d > /tmp/gcp-credentials.json
    export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp-credentials.json
    echo "GCP credentials file created at /tmp/gcp-credentials.json"
else
    echo "GCP_SA_KEY_BASE64 not provided, using VM service account"
fi

# Always run migrations (they're safe and necessary)
echo "Running Django Migrations"
echo "Running djstripe migrations first..."
python manage.py migrate djstripe --noinput
echo "Running all other migrations..."
python manage.py migrate --noinput

# Check if we should skip collectstatic
if [ "${SKIP_COLLECTSTATIC:-False}" = "True" ]; then
  echo "SKIP_COLLECTSTATIC=True, skipping collectstatic"
else
  echo "Running collectstatic with production settings (GCS)"
  python manage.py collectstatic --noinput --clear
fi

# Check if we should skip data loading commands
if [ "${SKIP_DATA_LOADING:-False}" = "True" ]; then
  echo "SKIP_DATA_LOADING=True, skipping data loading commands"
else
  echo "Running data loading commands"
  python manage.py load_model_providers 
  # python manage.py load_agent_instructions 
  # python manage.py load_agent_outputs
  # python manage.py load_apps
fi


# Check if we should enable HTTPS
if [ "${ENABLE_HTTPS:-0}" = "1" ] && [ -f "/code/ssl/cert.pem" ] && [ -f "/code/ssl/key.pem" ]; then
  echo "Running gunicorn with both HTTP and HTTPS support"
  gunicorn --bind 0.0.0.0:$HTTP_PORT --workers 1 --threads 4 --timeout 0 bh_opie.asgi:application -k uvicorn.workers.UvicornWorker &
  gunicorn --bind 0.0.0.0:$HTTPS_PORT --workers 1 --threads 4 --timeout 0 \
    --certfile=/code/ssl/cert.pem --keyfile=/code/ssl/key.pem \
    bh_opie.asgi:application -k uvicorn.workers.UvicornWorker
else
  echo "Running gunicorn with HTTP support only"
  gunicorn --bind 0.0.0.0:$HTTP_PORT --workers 1 --threads 8 --timeout 0 bh_opie.asgi:application -k uvicorn.workers.UvicornWorker
fi