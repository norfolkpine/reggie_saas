#!/bin/bash
# Script to create service accounts and GCS buckets for bh-reggie-test (test/staging)
# Usage: bash deploy/gcp-create-service-accounts-and-buckets.sh

set -euo pipefail

PROJECT_ID="bh-reggie-test"
REGION="us-central1"

gcloud config set project "$PROJECT_ID"

# Service Account names
CLOUD_RUN_SA="cloud-run-test"
GITHUB_ACTIONS_SA="github-actions-test"

# Bucket names
STATIC_BUCKET="bh-reggie-test-static"
MEDIA_BUCKET="bh-reggie-test-media"
DOCS_BUCKET="bh-reggie-test-docs"

# 1. Create Service Accounts
echo "Creating service accounts..."
gcloud iam service-accounts create "$CLOUD_RUN_SA" \
  --project="$PROJECT_ID" \
  --display-name="Cloud Run Test Service Account" || true
gcloud iam service-accounts create "$GITHUB_ACTIONS_SA" \
  --project="$PROJECT_ID" \
  --display-name="GitHub Actions Test Service Account" || true

# 2. Assign roles (customize as needed)
echo "Assigning roles..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$CLOUD_RUN_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$CLOUD_RUN_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$GITHUB_ACTIONS_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# 3. Create GCS Buckets
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
echo "Buckets:"
echo "  gs://$STATIC_BUCKET"
echo "  gs://$MEDIA_BUCKET"
echo "  gs://$DOCS_BUCKET"
