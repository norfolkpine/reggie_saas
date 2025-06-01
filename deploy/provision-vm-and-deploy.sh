#!/bin/bash
# Provision a GCP VM and deploy Django, Redis, and Yjs using Docker Compose
# Usage: bash deploy/provision-vm-and-deploy.sh
set -euo pipefail

# Source deployment.env for shared variables
DEPLOY_ENV="$(dirname "$0")/deployment.env"
if [ -f "$DEPLOY_ENV" ]; then
  echo "Sourcing deployment environment from $DEPLOY_ENV"
  set -a
  source "$DEPLOY_ENV"
  set +a
fi

VM_NAME=${VM_NAME:-reggie-stack-vm}
ZONE=${ZONE:-us-central1-a}
MACHINE_TYPE=${MACHINE_TYPE:-e2-medium}
IMAGE_FAMILY=${IMAGE_FAMILY:-ubuntu-2204-lts}
IMAGE_PROJECT=${IMAGE_PROJECT:-ubuntu-os-cloud}
PROJECT_ID=${PROJECT_ID:-bh-reggie-test}

# 1. Create the VM if it doesn't exist
if ! gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "Creating VM $VM_NAME in $ZONE..."
  gcloud compute instances create "$VM_NAME" \
    --zone="$ZONE" \
    --machine-type="$MACHINE_TYPE" \
    --image-family="$IMAGE_FAMILY" \
    --image-project="$IMAGE_PROJECT" \
    --boot-disk-size=30GB \
    --tags=http-server,https-server \
    --project="$PROJECT_ID"
else
  echo "VM $VM_NAME already exists. Skipping creation."
fi

# 2. Copy project files to the VM
# (Assumes Docker Compose file and all needed app code are in reggie_saas/ directory)
VM_USER=ubuntu
REMOTE_PATH="/home/$VM_USER/reggie_saas"

# Ensure SSH key exists
if [ ! -f "$HOME/.ssh/google_compute_engine" ]; then
  echo "Generating SSH key for gcloud..."
  gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command="exit"
fi

echo "Copying project files to VM..."
gcloud compute scp --recurse ../../reggie_saas "$VM_USER@$VM_NAME:$REMOTE_PATH" --zone="$ZONE" --project="$PROJECT_ID"

# 3. Install Docker and Docker Compose on the VM, then deploy
STARTUP_SCRIPT=$(cat <<'EOS'
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo usermod -aG docker $USER
cd ~/reggie_saas
sudo docker-compose pull || true
sudo docker-compose up -d --build
EOS
)

echo "Running setup and deployment commands on VM..."
gcloud compute ssh "$VM_USER@$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command="$STARTUP_SCRIPT"

echo "Deployment to $VM_NAME complete."
