#!/bin/bash
# Create the smallest Cloud SQL PostgreSQL 16 instance with pgvector for bh-reggie-test
# Usage: bash deploy/gcp-create-cloudsql-pgvector.sh
# Sources deployment.env if present for shared variables
set -euo pipefail

DEPLOY_ENV="$(dirname "$0")/deployment.env"
if [ -f "$DEPLOY_ENV" ]; then
  echo "Sourcing deployment environment from $DEPLOY_ENV"
  set -a
  source "$DEPLOY_ENV"
  set +a
fi

PROJECT_ID=${PROJECT_ID:-bh-reggie-test}
REGION=${REGION:-us-central1}
INSTANCE_NAME=${INSTANCE_NAME:-reggie-test-pg}
DB_NAME=${DB_NAME:-bh_reggie}
DB_USER=${DB_USER:-reggieuser}
DB_PASS=${DB_PASS:-reggiepass}
PG_VERSION=POSTGRES_15
TIER=db-f1-micro
STORAGE=10

# Enable Cloud SQL Admin API
if ! gcloud services list --enabled --project="$PROJECT_ID" | grep -q sqladmin.googleapis.com; then
  echo "Enabling Cloud SQL Admin API..."
  gcloud services enable sqladmin.googleapis.com --project="$PROJECT_ID"
fi

echo "Creating Cloud SQL instance ($INSTANCE_NAME)..."
gcloud sql instances create "$INSTANCE_NAME" \
  --database-version=$PG_VERSION \
  --tier=$TIER \
  --region=$REGION \
  --storage-type=SSD \
  --storage-size=$STORAGE \
  --root-password="$DB_PASS"

echo "Creating database ($DB_NAME)..."
gcloud sql databases create "$DB_NAME" --instance="$INSTANCE_NAME"

echo "Creating user ($DB_USER)..."
gcloud sql users create "$DB_USER" --instance="$INSTANCE_NAME" --password="$DB_PASS"

# Enable pgvector extension
cat <<EOF > /tmp/enable_pgvector.sql
CREATE EXTENSION IF NOT EXISTS vector;
EOF

echo "Enabling pgvector extension..."
gcloud sql connect "$INSTANCE_NAME" --user=postgres --quiet --project="$PROJECT_ID" --command="$(cat /tmp/enable_pgvector.sql)"
rm /tmp/enable_pgvector.sql

echo "Granting Cloud Run service account access..."
gcloud sql instances add-iam-policy-binding "$INSTANCE_NAME" \
  --member="serviceAccount:${CLOUD_RUN_SA}" \
  --role="roles/cloudsql.client"

echo "Cloud SQL instance ($INSTANCE_NAME) with pgvector is ready."
