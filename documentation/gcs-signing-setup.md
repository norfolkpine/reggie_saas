# GCS Signed URL Setup and Testing Guide

## Overview

This document explains how to set up Google Cloud Storage (GCS) signed URLs using service account impersonation for secure, time-limited access to private files without requiring authentication.

## Why Service Account Impersonation?

### The Problem
- **VM Service Accounts** (`<project-id>-vm-sa@<project-id>.iam.gserviceaccount.com`) don't have private keys for signing
- **Direct Service Account Keys** are security risks and hard to manage
- **Signed URLs** require private keys for cryptographic signing

### The Solution
- **Service Account Impersonation** allows the VM service account to act as a dedicated signing service account
- **No Private Keys** stored in the application
- **Google-Blessed Approach** using metadata service authentication

## Service Account Architecture

```
┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
│   VM Instance   │───▶│  VM Service Account  │───▶│ GCS Signing Service │
│                 │    │  <vm-service-account> │    │      Account        │
│                 │    │  @<project-id>.iam    │    │ gcs-signing-sa@     │
│                 │    │  .gserviceaccount.com │    │ <project-id>.iam    │
└─────────────────┘    └──────────────────────┘    │ .gserviceaccount.com│
                                                    └─────────────────────┘
```

### Service Accounts Explained

1. **VM Service Account** (`<vm-service-account-name>@<project-id>.iam.gserviceaccount.com`)
   - Attached to the VM instance
   - Authenticates via metadata service
   - Has permission to impersonate GCS signing service account
   - *Note: Service account name can be any valid identifier (e.g., `bh-opie-vm-sa`, `compute-engine-sa`, etc.)*

2. **GCS Signing Service Account** (`gcs-signing-sa@<project-id>.iam.gserviceaccount.com`)
   - Dedicated service account for signing operations
   - Has private key for cryptographic signing
   - Has `roles/storage.objectViewer` on GCS buckets

## Required IAM Permissions

### 1. VM Service Account Permissions
```bash
# Allow VM service account to impersonate GCS signing service account
gcloud iam service-accounts add-iam-policy-binding \
  gcs-signing-sa@<project-id>.iam.gserviceaccount.com \
  --member="serviceAccount:<vm-service-account-name>@<project-id>.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --project=<project-id>
```

### 2. GCS Signing Service Account Permissions
```bash
# Allow GCS signing service account to view objects in buckets
gcloud storage buckets add-iam-policy-binding gs://<project-id>-media \
  --member="serviceAccount:gcs-signing-sa@<project-id>.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"

gcloud storage buckets add-iam-policy-binding gs://<project-id>-static \
  --member="serviceAccount:gcs-signing-sa@<project-id>.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
```

## Environment Configuration

### Production Environment Variables
```bash
# Required for GCS signing
export GCS_IMPERSONATION_TARGET="gcs-signing-sa@<project-id>.iam.gserviceaccount.com"
export GOOGLE_CLOUD_PROJECT="<project-id>"
```

### Django Settings Integration
The Django application automatically:
1. Detects GCP environment via metadata service
2. Loads VM service account credentials
3. Sets up impersonation if `GCS_IMPERSONATION_TARGET` is configured
4. Falls back to service account key if impersonation fails

## Testing Commands

### 1. Test Service Account Impersonation
```bash
# SSH into VM and test impersonation
gcloud compute ssh <vm-name> --zone=<zone> --project=<project-id> \
  --command="gcloud auth print-access-token --impersonate-service-account=gcs-signing-sa@<project-id>.iam.gserviceaccount.com"
```

**Expected Result**: Access token returned successfully

### 2. Test Signed URL Generation
```bash
# Test signed URL generation with impersonation
gcloud compute ssh <vm-name> --zone=<zone> --project=<project-id> \
  --command="gcloud storage sign-url gs://<project-id>-media/test-file.txt --duration=1h --impersonate-service-account=gcs-signing-sa@<project-id>.iam.gserviceaccount.com"
```

**Expected Result**: Signed URL with signature parameters

### 3. Test Django Management Command
```bash
# SSH into VM and run Django test
gcloud compute ssh <vm-name> --zone=<zone> --project=<project-id> \
  --command="cd /path/to/app && export GCS_IMPERSONATION_TARGET='gcs-signing-sa@<project-id>.iam.gserviceaccount.com' && python manage.py test_gcs_signed_urls"
```

**Expected Result**: 
- ✅ Test file created successfully
- ✅ Signed URL generated with signature parameters
- ✅ Test file cleaned up

### 4. Test Docker Environment
```bash
# Test in Docker Compose environment
export GCS_IMPERSONATION_TARGET="gcs-signing-sa@<project-id>.iam.gserviceaccount.com"
docker-compose -f docker-compose.prod.yml exec web python manage.py test_gcs_signed_urls

# Or run the comprehensive Docker test script
./scripts/test_gcs_docker.sh
```

### 5. Test Credential Loading Only
```bash
# Set environment variables
export GCS_IMPERSONATION_TARGET="gcs-signing-sa@<project-id>.iam.gserviceaccount.com"

# Run credential test script
python scripts/test_gcs_credentials.py
```

## Troubleshooting

### Common Issues

#### 1. Permission Denied Errors
```
ERROR: PERMISSION_DENIED: Failed to impersonate [gcs-signing-sa@<project-id>.iam.gserviceaccount.com]
```

**Solution**: Verify IAM permissions are correctly set:
```bash
# Check VM service account can impersonate GCS signing SA
gcloud iam service-accounts get-iam-policy gcs-signing-sa@<project-id>.iam.gserviceaccount.com
```

#### 2. Bucket Access Errors
```
ERROR: Failed to auto-detect the region for <bucket-name>
```

**Solution**: Grant bucket permissions to GCS signing service account:
```bash
gcloud storage buckets add-iam-policy-binding gs://<bucket-name> \
  --member="serviceAccount:gcs-signing-sa@<project-id>.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
```

#### 3. Credential Loading Errors
```
AttributeError: you need a private key to sign credentials
```

**Solution**: Ensure `GCS_IMPERSONATION_TARGET` environment variable is set correctly.

### Verification Commands

#### Check Service Account Exists
```bash
gcloud iam service-accounts describe gcs-signing-sa@<project-id>.iam.gserviceaccount.com
```

#### Check IAM Bindings
```bash
# Check VM service account permissions
gcloud iam service-accounts get-iam-policy gcs-signing-sa@<project-id>.iam.gserviceaccount.com

# Check bucket permissions
gcloud storage buckets get-iam-policy gs://<project-id>-media
```

#### Check VM Service Account
```bash
# Get the VM service account email
gcloud compute instances describe <vm-name> --zone=<zone> --project=<project-id> \
  --format="value(serviceAccounts[0].email)"

# Example output: bh-opie-vm-sa@bh-opie.iam.gserviceaccount.com
```

## Security Best Practices

1. **Least Privilege**: Only grant necessary permissions
2. **No Private Keys**: Use impersonation instead of service account keys
3. **Environment Variables**: Store configuration in environment variables
4. **Regular Audits**: Review IAM permissions regularly
5. **Monitoring**: Monitor signed URL usage and access patterns

## Terraform Integration

The GCS signing service account and permissions are managed via Terraform:

```hcl
# GCS Signing Service Account
resource "google_service_account" "gcs_signing" {
  account_id   = "gcs-signing-sa"
  display_name = "GCS Signing Service Account"
  description  = "Service account for GCS signed URL operations"
}

# IAM roles for GCS Signing Service Account
resource "google_project_iam_member" "gcs_signing_storage_object_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.gcs_signing.email}"
}

# Enable VM service account to impersonate the GCS signing service account
resource "google_service_account_iam_member" "vm_impersonate_gcs_signing" {
  service_account_id = google_service_account.gcs_signing.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.vm_service_account.email}"
}
```

## Deployment Checklist

- [ ] GCS signing service account created
- [ ] VM service account has impersonation permissions
- [ ] GCS signing service account has bucket permissions
- [ ] Environment variable `GCS_IMPERSONATION_TARGET` set
- [ ] Django settings configured for production
- [ ] Terraform applied with new resources
- [ ] Tests passing on VM
- [ ] Signed URL generation working in production

## References

- [Google Cloud Service Account Impersonation](https://cloud.google.com/iam/docs/impersonating-service-accounts)
- [GCS Signed URLs](https://cloud.google.com/storage/docs/access-control/signed-urls)
- [Django Storages GCS Backend](https://django-storages.readthedocs.io/en/latest/backends/gcloud.html)
