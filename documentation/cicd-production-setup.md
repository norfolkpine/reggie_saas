# CI/CD Production Setup with Private Networking

This guide covers setting up GitHub Actions CI/CD for production deployment with private networking, IAP access, and Cloudflare tunnels.

## Overview

With private networking enabled, traditional CI/CD approaches need modification. This guide provides three production-ready solutions:

1. **GitHub Actions + IAP** (Recommended for VM deployment)
2. **Cloud Build + IAP** (Alternative for VM deployment)
3. **Cloud Run** (Most scalable, serverless)

## Architecture

```
GitHub Actions → GCP Service Account → IAP Tunnel → Private VM → Cloudflare Tunnel → Internet
```

## Prerequisites

- Private GCP infrastructure deployed via Terraform
- IAP access configured
- Service accounts with proper permissions
- Cloudflare tunnel setup (optional)

---

## Option 1: GitHub Actions + IAP (VM Deployment)

### Service Account Setup

The GitHub Actions workflow uses a service account with IAP permissions:

```hcl
# In terraform/environments/prod/main.tf
resource "google_service_account" "github_actions_production" {
  account_id   = "github-actions-production"
  display_name = "GitHub Actions Production Service Account"
}

# IAP permissions
resource "google_project_iam_member" "github_actions_iap_tunnel" {
  project = var.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = "serviceAccount:${google_service_account.github_actions_production.email}"
}
```

### Required IAM Roles

The service account needs these roles:
- `roles/iap.tunnelResourceAccessor` - Access IAP tunnels
- `roles/compute.instanceAdmin` - Manage VM instances
- `roles/storage.admin` - Access storage buckets
- `roles/cloudsql.client` - Access CloudSQL
- `roles/iam.serviceAccountUser` - Impersonate other service accounts

### GitHub Secrets Setup

1. **Create Service Account Key**:
   ```bash
   gcloud iam service-accounts keys create github-actions-key.json \
     --iam-account=github-actions-production@bh-opie.iam.gserviceaccount.com \
     --project=bh-opie
   
   # Base64 encode for GitHub secret
   base64 -i github-actions-key.json
   ```

2. **Add GitHub Repository Secrets**:
   - `GCP_SA_KEY`: Base64-encoded service account key
   - `SSH_PRIVATE_KEY`: SSH key for VM access (if needed)
   - `SSH_USER`: Username for VM access
   - `SECRET_KEY`: Django secret key
   - `DATABASE_URL`: Database connection string
   - `DJANGO_DATABASE_HOST`: Database host
   - `SYSTEM_API_KEY`: System API key
   - `GCP_SA_KEY_BASE64`: Base64-encoded service account key
   - `GCS_STORAGE_JSON_BASE64`: Base64-encoded storage credentials

### Workflow Configuration

The workflow file `.github/workflows/deploy-production.yml` handles:

1. **Authentication**: Uses service account credentials
2. **Docker Build**: Builds and pushes images to GCR
3. **IAP Access**: Connects to private VM via IAP
4. **Deployment**: Deploys application using Docker Compose

### Key Features

- ✅ **No Public IPs**: Uses IAP for secure access
- ✅ **Identity-Based**: Uses Google's identity system
- ✅ **Audit Trail**: All access is logged
- ✅ **Secure**: End-to-end encryption

---

## Option 2: Cloud Build + IAP

### Cloud Build Configuration

Use `cloudbuild-production.yaml` for Cloud Build deployment:

```yaml
steps:
  # Build and push Docker images
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/reggie-web:latest', '.']
  
  # Deploy via IAP
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        gcloud compute ssh opie-stack-vm \
          --zone=australia-southeast1-a \
          --project=$PROJECT_ID \
          --tunnel-through-iap \
          --command="deployment-commands"
```

### Trigger Setup

```bash
# Create Cloud Build trigger
gcloud builds triggers create github \
  --repo-name=reggie_saas \
  --repo-owner=your-username \
  --branch-pattern="^main$" \
  --build-config=cloudbuild-production.yaml
```

---

## Option 3: Cloud Run (Serverless)

### VPC Connector Setup

For Cloud Run to access private resources, create a VPC connector:

```hcl
# Add to terraform/environments/prod/main.tf
resource "google_vpc_access_connector" "production_connector" {
  name          = "production-connector"
  ip_cidr_range = "10.8.0.0/28"
  network       = google_compute_network.vpc_network.name
  region        = var.region
  
  depends_on = [google_project_service.vpcaccess_api]
}
```

### Cloud Run Deployment

Use `.github/workflows/deploy-cloudrun.yml` for serverless deployment:

```yaml
- name: Deploy to Cloud Run
  run: |
    gcloud run deploy reggie-web \
      --image gcr.io/$PROJECT_ID/reggie-web:latest \
      --region $REGION \
      --platform managed \
      --vpc-connector projects/$PROJECT_ID/locations/$REGION/connectors/production-connector \
      --vpc-egress all-traffic
```

### Benefits

- ✅ **Auto-scaling**: Scales based on demand
- ✅ **Pay-per-use**: Only pay for actual usage
- ✅ **Zero maintenance**: No VM management
- ✅ **High availability**: Built-in redundancy

---

## Security Considerations

### IAP Access Control

```hcl
# Restrict IAP access to specific groups
resource "google_project_iam_member" "iap_tunnel_resource_accessor" {
  project = var.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = "group:${var.admin_email}"
}
```

### Service Account Permissions

Follow principle of least privilege:

```hcl
# Minimal required permissions
resource "google_project_iam_member" "github_actions_minimal" {
  project = var.project_id
  role    = "roles/compute.instanceAdmin"
  member  = "serviceAccount:${google_service_account.github_actions_production.email}"
}
```

### Secret Management

Use Google Secret Manager for sensitive data:

```hcl
# Store secrets in Secret Manager
resource "google_secret_manager_secret" "github_actions_key" {
  secret_id = "github-actions-key"
  
  replication {
    auto {}
  }
}
```

---

## Monitoring and Logging

### Cloud Logging

Monitor deployment logs:

```bash
# View GitHub Actions logs
gcloud logging read "resource.type=gae_app" --limit=50

# View VM logs
gcloud logging read "resource.type=gce_instance" --limit=50
```

### Cloud Monitoring

Set up alerts for deployment failures:

```hcl
# Alert for failed deployments
resource "google_monitoring_alert_policy" "deployment_failure" {
  display_name = "Deployment Failure Alert"
  
  conditions {
    display_name = "Deployment failure"
    condition_threshold {
      filter = "resource.type=gae_app AND severity>=ERROR"
      duration = "300s"
      comparison = "COMPARISON_GREATER_THAN"
      threshold_value = 0
    }
  }
}
```

---

## Troubleshooting

### Common Issues

#### 1. IAP Access Denied
```bash
# Check IAM permissions
gcloud projects get-iam-policy bh-opie

# Verify service account has IAP role
gcloud projects get-iam-policy bh-opie \
  --flatten="bindings[].members" \
  --format="table(bindings.role)" \
  --filter="bindings.members:github-actions-production@bh-opie.iam.gserviceaccount.com"
```

#### 2. VM Connection Failed
```bash
# Test IAP connection manually
gcloud compute ssh opie-stack-vm \
  --zone=australia-southeast1-a \
  --project=bh-opie \
  --tunnel-through-iap \
  --command="echo 'Connection successful'"
```

#### 3. Docker Build Failed
```bash
# Check GCR permissions
gcloud auth configure-docker gcr.io

# Verify service account can push to GCR
gcloud auth activate-service-account \
  --key-file=github-actions-key.json
```

### Debug Commands

```bash
# Check VM status
gcloud compute instances describe opie-stack-vm \
  --zone=australia-southeast1-a \
  --project=bh-opie

# Check IAP status
gcloud iap web get-iam-policy \
  --resource-type=compute \
  --project=bh-opie

# Check service account permissions
gcloud projects get-iam-policy bh-opie \
  --flatten="bindings[].members" \
  --format="table(bindings.role)" \
  --filter="bindings.members:github-actions-production@bh-opie.iam.gserviceaccount.com"
```

---

## Best Practices

### 1. Security
- Use least privilege IAM roles
- Rotate service account keys regularly
- Enable audit logging
- Use Secret Manager for sensitive data

### 2. Reliability
- Implement health checks
- Use rolling deployments
- Set up monitoring and alerting
- Test rollback procedures

### 3. Performance
- Use appropriate machine types
- Implement caching strategies
- Monitor resource usage
- Optimize Docker images

### 4. Cost Optimization
- Use preemptible instances for non-critical workloads
- Implement auto-scaling
- Monitor resource usage
- Use committed use discounts

---

## Production Checklist

- [ ] Infrastructure deployed with private networking
- [ ] IAP access configured for admin group
- [ ] Service accounts created with minimal permissions
- [ ] GitHub secrets configured
- [ ] CI/CD workflow tested
- [ ] Monitoring and alerting configured
- [ ] Backup and recovery procedures documented
- [ ] Security review completed
- [ ] Performance testing completed
- [ ] Documentation updated

---

## Next Steps

1. **Deploy Infrastructure**: Run `terraform apply`
2. **Create Service Account Key**: Generate key for GitHub Actions
3. **Configure GitHub Secrets**: Add all required secrets
4. **Test Deployment**: Run the CI/CD workflow
5. **Set Up Monitoring**: Configure alerts and logging
6. **Document Procedures**: Update team documentation

---

**Note**: This setup provides enterprise-grade security with zero public attack surface while maintaining full CI/CD functionality through Google's IAP service.

