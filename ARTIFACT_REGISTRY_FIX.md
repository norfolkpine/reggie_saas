# Artifact Registry Authentication Fix

This document summarizes the fixes applied to resolve the 403 Forbidden error when pushing Docker images to Google Artifact Registry from GitHub Actions.

## Problem

GitHub Actions was failing with a 403 Forbidden error when trying to push Docker images to `australia-southeast1-docker.pkg.dev/bh-opie/containers/opie-web:latest`:

```
ERROR: failed to push australia-southeast1-docker.pkg.dev/bh-opie/containers/opie-web:latest: 
failed to authorize: failed to fetch anonymous token: unexpected status from GET request to 
https://australia-southeast1-docker.pkg.dev/v2/token?scope=repository%3Abh-opie%2Fcontainers%2Fopie-web%3Apull%2Cpush&service=australia-southeast1-docker.pkg.dev: 403 Forbidden
```

## Root Causes

1. **Outdated GitHub Actions authentication**: Using deprecated `google-github-actions/auth@v1`
2. **Incorrect Docker configuration**: Wrong Artifact Registry URL format
3. **Missing IAM permissions**: Service account lacked proper Artifact Registry roles
4. **Redundant IAM roles**: Had both `artifactregistry.writer` and `artifactregistry.admin`

## Fixes Applied

### 1. Updated GitHub Actions Workflow (`.github/workflows/deployment.yml`)

- ✅ Updated from `google-github-actions/auth@v1` to `google-github-actions/auth@v2`
- ✅ Fixed Docker configuration to use correct Artifact Registry URL: `australia-southeast1-docker.pkg.dev`
- ✅ Updated all Docker image references to use proper format: `australia-southeast1-docker.pkg.dev/bh-opie/containers/`
- ✅ Removed deprecated `ARTIFACT_REGISTRY_URL` environment variable

### 2. Updated Terraform Configuration (`infra/envs/prod/main.tf`)

- ✅ Added `roles/artifactregistry.reader` for pulling images
- ✅ Added `roles/storage.objectViewer` for additional operations
- ✅ Removed redundant `roles/artifactregistry.admin` role
- ✅ Kept essential roles: `artifactregistry.writer`, `artifactregistry.repoAdmin`

### 3. Created Helper Scripts

- ✅ `scripts/fix-artifact-registry-permissions.sh` - Manual permission setup
- ✅ `scripts/test-docker-auth.sh` - Test Docker authentication locally
- ✅ `scripts/apply-terraform-iam-fixes.sh` - Apply Terraform changes

## Current IAM Roles for GitHub Actions Service Account

The `github-actions@bh-opie.iam.gserviceaccount.com` service account now has:

- `roles/artifactregistry.writer` - Push images to Artifact Registry
- `roles/artifactregistry.reader` - Pull images from Artifact Registry
- `roles/artifactregistry.repoAdmin` - Manage repository settings
- `roles/storage.objectViewer` - Access storage objects
- `roles/storage.admin` - Full storage access
- `roles/storage.objectAdmin` - Manage storage objects
- `roles/storage.objectCreator` - Create storage objects
- `roles/run.admin` - Deploy to Cloud Run
- `roles/iam.serviceAccountUser` - Use service accounts
- `roles/secretmanager.secretAccessor` - Access secrets

## Next Steps

1. **Apply Terraform changes**:
   ```bash
   ./scripts/apply-terraform-iam-fixes.sh
   ```

2. **Test locally** (optional):
   ```bash
   ./scripts/test-docker-auth.sh
   ```

3. **Test GitHub Actions**: Push to main branch to trigger the workflow

## Verification

After applying the fixes, your GitHub Actions workflow should successfully:
- Authenticate with Google Cloud
- Configure Docker for Artifact Registry
- Build Docker images
- Push images to `australia-southeast1-docker.pkg.dev/bh-opie/containers/`

The 403 Forbidden error should be completely resolved.

## Files Modified

- `.github/workflows/deployment.yml` - Updated GitHub Actions workflow
- `infra/envs/prod/main.tf` - Updated IAM roles
- `scripts/fix-artifact-registry-permissions.sh` - Manual permission script
- `scripts/test-docker-auth.sh` - Docker authentication test
- `scripts/apply-terraform-iam-fixes.sh` - Terraform apply script
