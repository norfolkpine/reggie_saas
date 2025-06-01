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
INSTANCE_NAME=${INSTANCE_NAME:-db0}
DB_NAME=${DB_NAME:-bh_reggie_test}
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
  --availability-type=ZONAL \
  --root-password="$DB_PASS"  # Force Standard Edition (no HA)

echo "Creating database ($DB_NAME)..."
gcloud sql databases create "$DB_NAME" --instance="$INSTANCE_NAME"

echo "Creating user ($DB_USER)..."
gcloud sql users create "$DB_USER" --instance="$INSTANCE_NAME" --password="$DB_PASS"

# Enable pgvector extension (manual step required)
echo "\n==== Manual Step Required: Enable pgvector extension ===="
echo "Connect to your Cloud SQL instance and run:"
echo "\n  gcloud sql connect $INSTANCE_NAME --user=\$DB_USER --project=$PROJECT_ID --database=$DB_NAME\n"
echo "At the psql prompt, run:"
echo "\n  CREATE EXTENSION IF NOT EXISTS vector;\n"
echo "If you get a permission error, you may need to set a password for the 'postgres' user and connect as 'postgres'. See the script comments for details."

echo "Granting Cloud Run service account access..."
gcloud sql instances add-iam-policy-binding "$INSTANCE_NAME" \
  --member="serviceAccount:${CLOUD_RUN_SA}" \
  --role="roles/cloudsql.client"

echo "Cloud SQL instance ($INSTANCE_NAME) with pgvector is ready."
