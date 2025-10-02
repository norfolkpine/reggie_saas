#!/bin/bash
# Script to create service accounts and GCS buckets for bh-opie (test/staging)
# Usage: bash deploy/gcp-create-service-accounts-and-buckets.sh

set -euo pipefail

DEPLOY_ENV="$(dirname "$0")/deployment.env"
if [ -f "$DEPLOY_ENV" ]; then
  echo "Sourcing deployment environment from $DEPLOY_ENV"
  set -a
  source "$DEPLOY_ENV"
  set +a
fi

gcloud config set project "$PROJECT_ID"

# Enable required APIs (Artifact Registry is needed for container builds and pushes)
echo "Enabling Artifact Registry API..."
gcloud services enable artifactregistry.googleapis.com --project "$PROJECT_ID"

# Service Account names and their roles (least-privilege, based on bh-crypto):
# - $CLOUD_RUN_SA:          roles/run.admin, roles/storage.objectAdmin, roles/cloudsql.client, roles/secretmanager.secretAccessor, roles/logging.logWriter
# - $GITHUB_ACTIONS_SA:     roles/artifactregistry.admin, roles/artifactregistry.writer, roles/cloudbuild.builds.builder, roles/cloudbuild.loggingServiceAgent, roles/cloudfunctions.invoker, roles/cloudscheduler.admin, roles/cloudsql.admin, roles/cloudsql.client, roles/containerregistry.ServiceAgent, roles/logging.admin, roles/run.admin, roles/run.invoker, roles/secretmanager.secretAccessor, roles/storage.admin, roles/storage.objectViewer, roles/iam.serviceAccountUser
#   # (No 'roles/owner'. Add/remove roles as needed for your CI/CD pipeline.)
# - $CLOUD_STORAGE_BACKUP_SA: roles/storage.objectAdmin, roles/serviceusage.serviceUsageConsumer
# - $OPIE_STORAGE_SA:     roles/storage.admin, roles/storage.bucketViewer, roles/storage.objectAdmin, roles/storage.objectViewer
#   # TODO: Add custom role if needed (e.g., CustomCloudStorageViewer)
# - $SQL_BACKUP_SA:         roles/cloudsql.admin, roles/storage.objectAdmin
CLOUD_RUN_SA="cloud-run-test"
GITHUB_ACTIONS_SA="github-actions-test"
CLOUD_STORAGE_BACKUP_SA="cloud-storage-backup"
OPIE_STORAGE_SA="bh-opie-storage"
SQL_BACKUP_SA="sql-backup"

# Bucket names
STATIC_BUCKET="bh-opie-static"
MEDIA_BUCKET="bh-opie-media"
DOCS_BUCKET="bh-opie-docs"

# 1. Create Service Accounts
echo "Creating service accounts..."
gcloud iam service-accounts create "$CLOUD_RUN_SA" \
  --project="$PROJECT_ID" \
  --display-name="Cloud Run Test Service Account" || true
gcloud iam service-accounts create "$GITHUB_ACTIONS_SA" \
  --project="$PROJECT_ID" \
  --display-name="GitHub Actions Test Service Account" || true
gcloud iam service-accounts create "$CLOUD_STORAGE_BACKUP_SA" \
  --project="$PROJECT_ID" \
  --display-name="Cloud Storage Backup Service Account" || true
gcloud iam service-accounts create "$OPIE_STORAGE_SA" \
  --project="$PROJECT_ID" \
  --display-name="Opie AI Cloud Storage Service Account" || true
gcloud iam service-accounts create "$SQL_BACKUP_SA" \
  --project="$PROJECT_ID" \
  --display-name="Cloud SQL Backup" || true

# 2. Assign roles (least-privilege, based on bh-crypto)
echo "Assigning roles..."
# Cloud Run Service Account
# (Run admin, object admin for storage, SQL client, Secret Manager, Logging)
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$CLOUD_RUN_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/run.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$CLOUD_RUN_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/storage.objectAdmin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$CLOUD_RUN_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/cloudsql.client"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$CLOUD_RUN_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$CLOUD_RUN_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/logging.logWriter"

# GitHub Actions Service Account
# (No owner, only necessary roles for CI/CD)
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/artifactregistry.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/cloudbuild.builds.builder"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/cloudbuild.loggingServiceAgent"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/cloudfunctions.invoker"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/cloudscheduler.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/cloudsql.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/cloudsql.client"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/containerregistry.ServiceAgent"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/logging.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/run.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/run.invoker"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/storage.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/storage.objectViewer"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/iam.serviceAccountUser"

# Cloud Storage Backup
# (Object admin, service usage consumer)
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$CLOUD_STORAGE_BACKUP_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/storage.objectAdmin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$CLOUD_STORAGE_BACKUP_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/serviceusage.serviceUsageConsumer"

# Opie AI Cloud Storage Service Account
# (Storage admin, bucket viewer, object admin, object viewer)
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$OPIE_STORAGE_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/storage.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$OPIE_STORAGE_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/storage.bucketViewer"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$OPIE_STORAGE_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/storage.objectAdmin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$OPIE_STORAGE_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/storage.objectViewer"
# TODO: Add custom role if needed (e.g., CustomCloudStorageViewer)

# Cloud SQL Backup
# (Cloud SQL admin, storage object admin)
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SQL_BACKUP_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/cloudsql.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SQL_BACKUP_SA@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/storage.objectAdmin"

# 3. (Optional/Secure) Create and download service account keys
# Only create keys for SAs that must be used outside GCP (e.g., CI/CD, local dev). Prefer Workload Identity/OIDC where possible.
# Keys will be stored in .gcp/creds/. Existing files will not be overwritten.
echo "Creating service account keys (if needed)..."
mkdir -p .gcp/creds

if [ ! -f ".gcp/creds/${PROJECT_ID}-github-actions.json" ]; then
  gcloud iam service-accounts keys create ".gcp/creds/${PROJECT_ID}-github-actions.json" \
    --iam-account=$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com
else
  echo ".gcp/creds/${PROJECT_ID}-github-actions.json already exists, skipping."
fi

if [ ! -f ".gcp/creds/${PROJECT_ID}-storage.json" ]; then
  gcloud iam service-accounts keys create ".gcp/creds/${PROJECT_ID}-storage.json" \
    --iam-account=$OPIE_STORAGE_SA@$PROJECT_ID.iam.gserviceaccount.com
else
  echo ".gcp/creds/${PROJECT_ID}-storage.json already exists, skipping."
fi

if [ ! -f ".gcp/creds/${PROJECT_ID}-sql-backup.json" ]; then
  gcloud iam service-accounts keys create ".gcp/creds/${PROJECT_ID}-sql-backup.json" \
    --iam-account=$SQL_BACKUP_SA@$PROJECT_ID.iam.gserviceaccount.com
else
  echo ".gcp/creds/${PROJECT_ID}-sql-backup.json already exists, skipping."
fi

# 4. Create GCS Buckets
echo "Creating buckets..."
gsutil mb -p "$PROJECT_ID" -c STANDARD -l "$REGION" "gs://$STATIC_BUCKET" || true
gsutil mb -p "$PROJECT_ID" -c STANDARD -l "$REGION" "gs://$MEDIA_BUCKET" || true
gsutil mb -p "$PROJECT_ID" -c STANDARD -l "$REGION" "gs://$DOCS_BUCKET" || true

# 4. Public access for static bucket is restricted by organization policy.
# Static files must be served via signed URLs or authenticated endpoints if public access is required.

echo "Setup complete."
echo "Service Accounts:"
echo "  $CLOUD_RUN_SA@$PROJECT_ID.iam.gserviceaccount.com"
echo "  $GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com"
echo "  $CLOUD_STORAGE_BACKUP_SA@$PROJECT_ID.iam.gserviceaccount.com"
echo "Buckets:"
echo "  gs://$STATIC_BUCKET"
echo "  gs://$MEDIA_BUCKET"
echo "  gs://$DOCS_BUCKET"
echo "  $OPIE_STORAGE_SA@$PROJECT_ID.iam.gserviceaccount.com (Opie AI Cloud Storage Service Account)"
echo "  $SQL_BACKUP_SA@$PROJECT_ID.iam.gserviceaccount.com (Cloud SQL Backup)"
