# Infrastructure as Code

This directory contains Terraform configurations for managing the Opie SaaS infrastructure on Google Cloud Platform.

## Structure

```
terraform/
├── environments/
│   ├── dev/          # Development environment
│   ├── staging/      # Staging environment
│   └── prod/         # Production environment (current)
├── modules/          # Reusable Terraform modules
└── shared/           # Shared resources across environments
```

## Current Environment: Production

The production environment is configured for:
- **Project**: `bh-opie`
- **Region**: `australia-southeast1`
- **Zone**: `australia-southeast1-a`

## Resources

- **VM Instance**: `opie-stack-vm` (e2-medium, Debian 12)
- **CloudSQL**: PostgreSQL 15 with pgvector
- **Databases**: `postgres`, `bh_opie`, `bh_opie_test`
- **Service Accounts**: GitHub Actions, Storage, SQL Backup, etc.
- **Secrets**: Frontend, Backend, Y-Provider, etc.

## Usage

```bash
cd terraform/environments/prod
terraform init
terraform plan
terraform apply
```

## State Management

⚠️ **Important**: State files are excluded from git. Consider using remote state storage (Terraform Cloud, GCS) for production.
