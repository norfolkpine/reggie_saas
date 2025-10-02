#!/bin/bash
# DEPRECATED: Service accounts and buckets are now managed by Terraform
# This script is kept for reference but should not be run
# Use: cd infra/envs/prod && terraform apply

echo "WARNING: This script is deprecated!"
echo "Service accounts and buckets are now managed by Terraform."
echo ""
echo "To create infrastructure, run:"
echo "  cd infra/envs/prod"
echo "  terraform init"
echo "  terraform apply"
echo ""
echo "This script will exit without making any changes."
exit 0