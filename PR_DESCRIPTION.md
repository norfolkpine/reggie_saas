# Fix GCS Signed URL Generation with Direct Service Account Authentication

## Problem
The application was failing to generate Google Cloud Storage (GCS) signed URLs with the error:
```
AttributeError: you need a private key to sign credentials. The credentials you are currently using <class 'google.auth.compute_engine.credentials.Credentials'> just contains a token.
```

This occurred because the VM service account credentials don't have private keys needed for cryptographic signing operations.

## Solution
Instead of using service account impersonation, we now use the `bh-opie-storage@bh-opie.iam.gserviceaccount.com` service account directly, which has:
- ✅ Private key for signing operations
- ✅ Direct bucket permissions (`roles/storage.objectAdmin`)
- ✅ Simplified architecture without impersonation complexity

## Changes Made

### 1. Django Settings (`bh_opie/settings.py`)
- **Removed impersonation logic** and complex credential fallback chains
- **Prioritized service account key** from `GCP_SA_KEY_BASE64` environment variable
- **Moved GCS configuration to class level** to ensure proper Django settings loading
- **Added comprehensive debug logging** for troubleshooting
- **Simplified credential loading** with clear priority order:
  1. `GCP_SA_KEY_BASE64` (base64-encoded service account key)
  2. `/tmp/gcp-credentials.json` (file-based service account key)
  3. VM service account (fallback, limited signing capabilities)

### 2. GitHub Actions Workflow (`.github/workflows/deployment.yml`)
- **Removed `GCS_IMPERSONATION_TARGET`** environment variable references
- **Kept `GCP_SA_KEY_BASE64`** from GitHub secrets for service account key
- **Simplified deployment configuration**

### 3. Docker Compose (`docker-compose.prod.yml`)
- **Removed `GCS_IMPERSONATION_TARGET`** environment variable
- **Kept `GCP_SA_KEY_BASE64`** for service account key configuration
- **Simplified environment variable setup**

### 4. Test Scripts
- **Updated `scripts/test_gcs_credentials.py`**:
  - Removed duplicate tests and impersonation logic
  - Fixed Django module path resolution
  - Enhanced service account key testing
  - Added comprehensive Django storage configuration testing
- **Updated `scripts/test_gcs_docker.sh`**:
  - Replaced default credentials test with service account key test
  - Added fallback to file-based credentials
  - Enhanced credential validation

## Architecture Change

### Before (Impersonation)
```
VM Instance → VM Service Account → Impersonate → GCS Signing SA → GCS Buckets
```

### After (Direct Service Account)
```
VM Instance → bh-opie-storage SA (with private key) → GCS Buckets
```

## Testing
- ✅ **Local testing confirmed** signed URL generation works with `bh-opie-storage` service account
- ✅ **Test scripts updated** and working correctly
- ✅ **Django storage configuration** properly configured
- ✅ **Service account credentials** loaded successfully

## Required GitHub Secret
Ensure `GCP_SA_KEY_BASE64` is set in GitHub repository secrets with the base64-encoded `bh-opie-storage` service account key JSON.

## IAM Permissions Required
The `bh-opie-storage@bh-opie.iam.gserviceaccount.com` service account needs:
- `roles/storage.objectAdmin` on `bh-opie-media` bucket
- `roles/storage.objectAdmin` on `bh-opie-static` bucket

## Benefits
1. **Simplified Architecture**: No impersonation complexity
2. **Better Performance**: Direct authentication without impersonation overhead
3. **Easier Debugging**: Clear credential loading with debug logging
4. **More Reliable**: Fewer moving parts and potential failure points
5. **Cleaner Code**: Removed complex impersonation logic

## Files Changed
- `bh_opie/settings.py` - Main GCS configuration
- `.github/workflows/deployment.yml` - Deployment workflow
- `docker-compose.prod.yml` - Docker environment variables
- `scripts/test_gcs_credentials.py` - Credential testing script
- `scripts/test_gcs_docker.sh` - Docker testing script

## Verification
After deployment, verify the fix by running:
```bash
# On the VM
python manage.py test_gcs_signed_urls
```

This should successfully generate signed URLs without the private key error.
