name: Terraform and Deploy

on:
  push:
    branches: [main]
    paths:
      - 'terraform/**'
      - 'deploy/**'
  workflow_dispatch:

jobs:
  terraform:
    name: 'Terraform Plan and Apply'
    runs-on: ubuntu-latest
    environment: production
    
    steps:
    - name: Checkout
      uses: actions/checkout@v4

    - name: Setup Terraform
      uses: hashicorp/setup-terraform@v3
      with:
        terraform_version: 1.6.0

    - name: Terraform Format Check
      run: terraform fmt -check -recursive terraform/

    - name: Terraform Init
      run: terraform init
      working-directory: terraform/environments/prod

    - name: Terraform Validate
      run: terraform validate
      working-directory: terraform/environments/prod

    - name: Terraform Plan
      run: terraform plan -out=tfplan
      working-directory: terraform/environments/prod

    - name: Terraform Apply
      run: terraform apply -auto-approve tfplan
      working-directory: terraform/environments/prod

    - name: Generate Deployment Config
      run: ./deploy/generate-deployment-env.sh

    - name: Upload deployment.env
      uses: actions/upload-artifact@v3
      with:
        name: deployment-env
        path: deployment.env

  deploy:
    name: 'Deploy Application'
    runs-on: ubuntu-latest
    needs: terraform
    if: github.ref == 'refs/heads/main'
    
    steps:
    - name: Checkout
      uses: actions/checkout@v4

    - name: Download deployment.env
      uses: actions/download-artifact@v3
      with:
        name: deployment-env
        path: .

    - name: Setup Google Cloud CLI
      uses: google-github-actions/setup-gcloud@v1
      with:
        credentials_json: '${{ secrets.GCP_SA_KEY }}'

    - name: Create Service Accounts and Buckets
      run: ./deploy/2_gcp-create-service-accounts-and-buckets.sh

    - name: Create Cloud SQL Instance
      run: ./deploy/3_gcp-create-cloudsql-pgvector.sh

    - name: Provision VM
      run: ./deploy/4_provision-vm-and-deploy.sh

    - name: Deploy Cloud Run Service
      run: ./deploy/5_deploy-cloudrun-llamaindex.sh
