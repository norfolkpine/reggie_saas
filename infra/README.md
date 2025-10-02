# Infrastructure as Code

This directory contains Terraform configurations for managing all infrastructure.

## Structure

```
infra/
├── bootstrap/          # One-time setup (run once)
│   ├── main.tf        # State bucket, deployer SA, WIF
│   ├── variables.tf   # Bootstrap variables
│   └── terraform.tfvars
└── envs/
    └── prod/          # Production environment
        ├── main.tf    # All app infrastructure
        ├── variables.tf
        └── terraform.tfvars
```

## Workflow

### 1. Bootstrap (Run Once)

Set up Terraform's own prerequisites:

```bash
cd infra/bootstrap
terraform init
terraform plan
terraform apply
```

This creates:
- Remote state bucket
- Terraform deployer service account
- Workload Identity Federation for GitHub Actions
- Required APIs

### 2. Production Environment

Deploy your application infrastructure:

```bash
cd infra/envs/prod
terraform init
terraform plan
terraform apply
```

This creates:
- Cloud SQL instance
- VM instance
- Service accounts for applications
- Storage buckets
- Secrets
- All IAM bindings

### 3. Application Deployment

After infrastructure is ready, deploy applications:

```bash
# Generate deployment config from Terraform
./deploy/generate-deployment-env.sh

# Deploy applications (manually)
./deploy/3_gcp-create-cloudsql-pgvector.sh  # Database setup
./deploy/4_provision-vm-and-deploy.sh       # VM provisioning
./deploy/5_deploy-cloudrun-llamaindex.sh    # Cloud Run deployment
```

## What's Managed by Terraform

- ✅ **Service Accounts** - All application service accounts
- ✅ **IAM Roles** - All role bindings
- ✅ **Storage Buckets** - Static, media, docs buckets
- ✅ **Cloud SQL** - Database instance and databases
- ✅ **VM Instance** - Compute instance
- ✅ **Secrets** - Secret Manager secrets
- ✅ **APIs** - Required Google Cloud APIs
- ✅ **Networking** - Firewall rules

## What's Still Manual

- 🔧 **Application Code** - Deployed via scripts
- 🔧 **Database Migrations** - Run via scripts
- 🔧 **Service Configuration** - Handled by deployment scripts

## Benefits

- ✅ **Single source of truth** - All infrastructure in Terraform
- ✅ **No drift** - Terraform manages everything
- ✅ **Auditable** - All changes tracked
- ✅ **Reproducible** - Easy to recreate environments
- ✅ **Secure** - No service account keys needed (uses WIF)

## Adding New Resources

1. Add resource to `infra/envs/prod/main.tf`
2. Add variables to `infra/envs/prod/variables.tf` if needed
3. Update `infra/envs/prod/terraform.tfvars` if needed
4. Run `terraform plan` and `terraform apply`

## Troubleshooting

**State locked?**
```bash
terraform force-unlock <lock-id>
```

**Need to import existing resources?**
```bash
terraform import google_sql_database_instance.db0 projects/bh-opie/instances/db0
```

**Want to see what Terraform will change?**
```bash
terraform plan
```
