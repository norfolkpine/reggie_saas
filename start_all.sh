#!/bin/bash

set -e

# Check for .env
if [ ! -f .env ]; then
  echo "⚠️  .env file not found! Please copy env.txt to .env and fill in your secrets."
  exit 1
fi

# Optionally, check Docker and Docker Compose availability
if ! command -v docker &> /dev/null; then
  echo "❌ Docker is not installed or not in PATH."
  exit 1
fi
if ! command -v docker-compose &> /dev/null; then
  echo "❌ docker-compose is not installed or not in PATH."
  exit 1
fi

# Start all services
echo "🚀 Building and starting all services with Docker Compose..."
docker-compose up --build

# Optionally, print URLs after startup
cat <<EOM

All services should now be running:
  Django:     http://localhost:8000
  Postgres:   localhost:5432 (service: db)
  Redis:      localhost:6379 (service: redis)
  y-provider: http://localhost:4444
  llamaindex: http://localhost:8080
EOM
