# Application Deployment

This directory contains scripts for deploying applications after infrastructure is ready.

## Prerequisites

**Infrastructure must be deployed first:**
```bash
# 1. Bootstrap (one-time)
cd infra/bootstrap
terraform init && terraform apply

# 2. Production environment
cd infra/envs/prod
terraform init && terraform apply
```

## Workflow

### 1. Generate Deployment Configuration
```bash
# Generate deployment.env from Terraform outputs
./deploy/generate-deployment-env.sh
```

### 2. Deploy Applications
```bash
# Database setup (if needed)
./deploy/3_gcp-create-cloudsql-pgvector.sh

# Check VM status and prepare for deployment
./deploy/check-vm-status.sh

# Cloud Run service deployment
./deploy/5_deploy-cloudrun-llamaindex.sh
```

## What's Managed Where

### Terraform (`infra/`)
- ✅ Service accounts and IAM
- ✅ Storage buckets
- ✅ Cloud SQL instance
- ✅ VM instance
- ✅ Secrets
- ✅ APIs and networking

### Deployment Scripts (`deploy/`)
- 🔧 Application code deployment
- 🔧 Database migrations
- 🔧 Service configuration
- 🔧 Cloud Run deployments

## Configuration Files

- **`infra/envs/prod/terraform.tfvars`** - Infrastructure configuration
- **`deployment.env`** - Generated from Terraform (DO NOT EDIT)
- **`deploy/1_deployment.env.example`** - Example file (for reference)

## Benefits

- ✅ **Infrastructure as Code** - All infrastructure in Terraform
- ✅ **No drift** - Terraform manages everything
- ✅ **Secure** - No service account keys needed
- ✅ **Reproducible** - Easy to recreate environments
- ✅ **Auditable** - All changes tracked

## Troubleshooting

**Infrastructure not ready?**
```bash
cd infra/envs/prod
terraform plan
terraform apply
```

**Missing deployment.env?**
```bash
./deploy/generate-deployment-env.sh
```

**Service accounts missing?**
```bash
cd infra/envs/prod
terraform apply  # Service accounts are now in Terraform
```
