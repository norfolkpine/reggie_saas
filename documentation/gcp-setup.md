# GCP Setup for bh-opie (Test/Staging)

This guide documents the setup of service accounts and Cloud Storage buckets for the test/staging environment in GCP project `bh-opie` (region: australia-southeast1).

## Service Accounts

- **cloud-run-test@bh-opie.iam.gserviceaccount.com**
  - Used by Cloud Run services to access GCP resources (e.g., Storage, Pub/Sub).
  - Roles: `roles/run.admin`, `roles/storage.admin`

- **github-actions-test@bh-opie.iam.gserviceaccount.com**
  - Used by GitHub Actions CI/CD workflows for deployment and artifact upload.
  - Roles: `roles/storage.admin`, `roles/run.admin`, `roles/iam.serviceAccountUser`
  - These additional roles allow GitHub Actions to deploy to Cloud Run and impersonate the Cloud Run service account securely.

## Buckets

- **bh-opie-static**: Static assets (CSS, JS, images, etc.)
  - _Note: Public access is restricted by GCP organization policy. Static files must be served securely (e.g., via signed URLs or authenticated endpoints)._
- **bh-opie-media**: User-uploaded files (profile pics, uploads, etc.)
- **bh-opie-docs**: Collaborative document storage (shared docs, etc.)
  - _Note: Bucket names must be globally unique. The 'bh-opie-' prefix is used for all test environment buckets to avoid naming conflicts and for clarity._

## Serving Static Files Securely in Django/GCP

Because public access to GCS buckets is disabled by policy, you have two main options:
- **Signed URLs:** Use `django-storages` with Google Cloud Storage and generate signed URLs for static files.
- **Authenticated Proxy:** Serve static files through your Django app or a custom endpoint that authenticates users before serving files.

See the [django-storages GCS documentation](https://django-storages.readthedocs.io/en/latest/backends/gcloud.html) for configuration details.

## Automated Setup

Run the following script to create the service accounts and buckets:

```sh
bash deploy/gcp-create-service-accounts-and-buckets.sh
```

> _Note: The script will automatically set the active gcloud project to `bh-opie` before running commands. If you encounter issues with resources being created in the wrong project, check your gcloud configuration with `gcloud config list`._
> _You must also have `gcloud` and `gsutil` installed and authenticated, and the project must exist._

## Next Steps
- Configure IAM permissions as needed for production.
- Store sensitive credentials in Secret Manager.
- Continue with Cloud Run and database setup.
