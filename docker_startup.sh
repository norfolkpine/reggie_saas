#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

HTTP_PORT=${PORT:-8000}
HTTPS_PORT=8443

echo "Running Django Migrations"
python manage.py migrate --noinput


mkdir -p /code/ssl

# Check if we should enable HTTPS
if [ "${ENABLE_HTTPS:-0}" = "1" ] && [ -f "/code/ssl/cert.pem" ] && [ -f "/code/ssl/key.pem" ]; then
  echo "Running gunicorn with both HTTP and HTTPS support"
  gunicorn --bind 0.0.0.0:$HTTP_PORT --workers 1 --threads 4 --timeout 0 bh_reggie.asgi:application -k uvicorn.workers.UvicornWorker &
  gunicorn --bind 0.0.0.0:$HTTPS_PORT --workers 1 --threads 4 --timeout 0 \
    --certfile=/code/ssl/cert.pem --keyfile=/code/ssl/key.pem \
    bh_reggie.asgi:application -k uvicorn.workers.UvicornWorker
else
  echo "Running gunicorn with HTTP support only"
  gunicorn --bind 0.0.0.0:$HTTP_PORT --workers 1 --threads 8 --timeout 0 bh_reggie.asgi:application -k uvicorn.workers.UvicornWorker
fi