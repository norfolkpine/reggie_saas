# Installation Guide V2 - Production Deployment

This guide provides step-by-step instructions for deploying the Opie SaaS application to production using Terraform, Cloud SQL, and Google Cloud Run.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Infrastructure Deployment (Terraform)](#infrastructure-deployment-terraform)
3. [Cloud SQL Proxy Setup](#cloud-sql-proxy-setup)
4. [GitHub Actions Secrets Configuration](#github-actions-secrets-configuration)
5. [Database Migration](#database-migration)
6. [Cloud Run API Key Creation](#cloud-run-api-key-creation)
7. [Application Deployment](#application-deployment)
8. [Verification](#verification)
9. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Tools
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (gcloud CLI)
- [Terraform](https://terraform.io/downloads) (>= 1.0)
- [Docker](https://docs.docker.com/get-docker/)
- [Python 3.12+](https://www.python.org/downloads/)
- [Node.js 18+](https://nodejs.org/) (for frontend)
- [Git](https://git-scm.com/downloads)

### Required Access
- Google Cloud Project with billing enabled
- Owner or Editor role on the GCP project
- GitHub repository with Actions enabled

### Environment Setup
```bash
# Clone the repository
git clone <repository-url>
cd reggie_saas

# Create Python virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements/requirements.txt
```

## Infrastructure Deployment (Terraform)

### 1. Bootstrap Terraform State (One-time setup)

```bash
cd infra/bootstrap
terraform init
terraform apply
```

This creates:
- GCS bucket for Terraform state
- Service accounts for deployment
- Basic project configuration

### 2. Deploy Production Infrastructure

```bash
cd infra/envs/prod
terraform init
terraform plan
terraform apply
```

This creates:
- Cloud SQL PostgreSQL instance with pgvector
- Cloud Run services
- Storage buckets
- Service accounts with proper IAM roles
- VPC network configuration
- Secrets in Secret Manager

### 3. Generate Deployment Configuration

```bash
# Generate deployment.env from Terraform outputs
./deploy/1_generate-deployment-env.sh
```

This creates `deployment.env` with all necessary configuration values.

## Cloud SQL Proxy Setup

### Option 1: Temporary Public IP (Recommended for Development)

For development and testing, you can use a script that temporarily enables public IP, starts the proxy, and disables it when done:

```bash
# Start Cloud SQL proxy with temporary public IP (simplest usage)
./scripts/cloudsql-proxy-with-temp-ip.sh

# Or with explicit start command
./scripts/cloudsql-proxy-with-temp-ip.sh --start

# The script will:
# 1. Enable public IP on Cloud SQL instance
# 2. Start the Cloud SQL proxy
# 3. Test the connection
# 4. Automatically disable public IP when you stop the script (Ctrl+C)
```

### Option 2: Permanent Public IP (For Production)

If you need persistent access, you can enable public IP permanently:

```bash
# Enable public IP permanently
gcloud sql instances patch db0 --project=bh-opie --assign-ip --quiet

# Verify public IP assignment
gcloud sql instances describe db0 --project=bh-opie --format="value(ipAddresses[0].ipAddress)"
```

### 3. Create Database User

```bash
# Run the Cloud SQL setup script
bash deploy/3_gcp-create-cloudsql-pgvector.sh
```

This script:
- Creates the `opieuser` database user
- Sets up pgvector extension
- Configures proper permissions

### 3. Start Cloud SQL Proxy

#### For Development (Local Machine)

##### Using the Temporary Public IP Script (Recommended)

```bash
# Start with temporary public IP (simplest usage)
./scripts/cloudsql-proxy-with-temp-ip.sh

# Or with explicit commands
./scripts/cloudsql-proxy-with-temp-ip.sh --start    # Start proxy
./scripts/cloudsql-proxy-with-temp-ip.sh --status   # Check status
./scripts/cloudsql-proxy-with-temp-ip.sh --test     # Test connection
./scripts/cloudsql-proxy-with-temp-ip.sh --stop     # Stop and cleanup
```

##### Using Docker Compose Directly

```bash
# Start the Cloud SQL proxy using Docker Compose
docker-compose -f docker-compose.cloudsql-proxy.yml up -d

# Verify proxy is running
docker logs reggie_saas-cloudsql-proxy-1
```

#### For Production (VM in Same VPC)

##### Option 1: Direct Binary (Recommended)

```bash
# Start Cloud SQL proxy directly
./scripts/start-cloudsql-proxy-production.sh --start-iam

# Check status
./scripts/start-cloudsql-proxy-production.sh --status

# Test connection
./scripts/start-cloudsql-proxy-production.sh --test
```

##### Option 2: Systemd Service (Production-Ready)

```bash
# Install as systemd service
sudo ./scripts/install-cloudsql-proxy-service.sh --install

# Copy service account credentials
sudo cp /path/to/service-account-key.json /opt/cloudsql-proxy/credentials.json
sudo chown cloudsql-proxy:cloudsql-proxy /opt/cloudsql-proxy/credentials.json
sudo chmod 600 /opt/cloudsql-proxy/credentials.json

# Start the service
sudo ./scripts/install-cloudsql-proxy-service.sh --start

# Check status
sudo ./scripts/install-cloudsql-proxy-service.sh --status

# View logs
sudo ./scripts/install-cloudsql-proxy-service.sh --logs
```

### 4. Test Database Connection

```bash
# Test connection with password
PGPASSWORD="your-db-password" psql -h localhost -p 5432 -U opieuser -d bh_opie -c "SELECT version();"
```

## GitHub Actions Secrets Configuration

### Required Secrets

Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

```bash
# GCP Service Account Key (JSON format)
GCP_SA_KEY={"type":"service_account","project_id":"bh-opie",...}

# Database credentials
DB_USER=opieuser
DB_PASSWORD=your-secure-password
DB_NAME=bh_opie
DB_HOST=localhost
DB_PORT=5432

# Django settings
SECRET_KEY=your-django-secret-key
DEBUG=False
ALLOWED_HOSTS=your-domain.com,api.your-domain.com

# API keys
OPENAI_API_KEY=sk-proj-...
GOOGLE_API_KEY=your-google-api-key
SYSTEM_API_KEY=your-system-api-key

# Cloud Run settings
CLOUD_RUN_SERVICE_URL=https://your-service.run.app
CLOUD_RUN_SA=cloud-run@bh-opie.iam.gserviceaccount.com
```

### How to Get Service Account Key

```bash
# Download service account key
gcloud iam service-accounts keys create github-actions-key.json \
  --iam-account=github-actions@bh-opie.iam.gserviceaccount.com \
  --project=bh-opie

# Copy the contents to GitHub Secrets
cat github-actions-key.json
```

## Database Migration

### 1. Set Environment Variables

```bash
# Set database connection variables
export DJANGO_DATABASE_HOST=localhost
export DJANGO_DATABASE_PORT=5432
export DJANGO_DATABASE_NAME=bh_opie
export DJANGO_DATABASE_USER=opieuser
export DJANGO_DATABASE_PASSWORD="your-db-password"
```

### 2. Run Migrations

```bash
# Create and apply migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Load initial data
python manage.py load_agent_instructions
python manage.py load_agent_outputs
python manage.py load_model_providers
python manage.py load_apps
```

## Cloud Run API Key Creation

### 1. Create System API Key

```bash
# Create Cloud Run API key
python manage.py create_cloud_run_api_key
```

This creates a system user and API key for Cloud Run services.

### 2. Update Cloud Run Environment

```bash
# Copy example environment file
cp cloudrun/bh-opie-llamaindex/env.example cloudrun/bh-opie-llamaindex/.env

# Edit the .env file with the generated API key
# DJANGO_API_KEY=your-generated-api-key
```

## Application Deployment

### 1. Build and Deploy Cloud Run Services

```bash
# Deploy LlamaIndex service
cd cloudrun/bh-opie-llamaindex
make build
make push
make deploy-service
```

### 2. Deploy Frontend (if applicable)

```bash
# Build frontend
cd frontend
npm install
npm run build

# Deploy to your hosting service (e.g., Vercel, Netlify)
```

### 3. Configure Domain and SSL

```bash
# Map custom domain to Cloud Run service
gcloud run domain-mappings create \
  --service=your-service \
  --domain=api.your-domain.com \
  --region=australia-southeast1
```

## Verification

### 1. Health Checks

```bash
# Check Django health
curl https://api.your-domain.com/health/

# Check Cloud Run service
curl https://your-service.run.app/health

# Check database connection
python manage.py dbshell --settings=bh_opie.settings
```

### 2. Test API Endpoints

```bash
# Test authentication
curl -X POST https://api.your-domain.com/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass"}'

# Test file upload
curl -X POST https://api.your-domain.com/api/files/upload/ \
  -H "Authorization: Bearer your-token" \
  -F "file=@test.pdf"
```

## Cloudflare Tunnel Setup

### 1. Install Cloudflare Tunnel

```bash
# Download and install cloudflared
# On macOS with Homebrew
brew install cloudflared

# On Linux
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# On Windows
# Download from: https://github.com/cloudflare/cloudflared/releases
```

### 2. Authenticate with Cloudflare

```bash
# Login to Cloudflare
cloudflared tunnel login

# This will open a browser window for authentication
# Select your domain and authorize the tunnel
```

### 3. Create Tunnel

```bash
# Create a new tunnel
cloudflared tunnel create opie-saas

# This will generate a tunnel ID and credentials file
# Note the tunnel ID for the next steps
```

### 4. Configure Tunnel

Create a tunnel configuration file:

```yaml
# ~/.cloudflared/config.yml
tunnel: your-tunnel-id
credentials-file: /home/user/.cloudflared/your-tunnel-id.json

ingress:
  # Django API
  - hostname: api.your-domain.com
    service: https://localhost:8000
    originRequest:
      noTLSVerify: true
  
  # Cloud Run LlamaIndex service
  - hostname: llamaindex.your-domain.com
    service: https://your-cloudrun-service.run.app
    originRequest:
      noTLSVerify: true
  
  # Frontend (if applicable)
  - hostname: app.your-domain.com
    service: https://localhost:3000
    originRequest:
      noTLSVerify: true
  
  # Catch-all rule (required)
  - service: http_status:404
```

### 5. Configure DNS Records

```bash
# Create CNAME records for your subdomains
# Run this command for each subdomain
cloudflared tunnel route dns your-tunnel-id api.your-domain.com
cloudflared tunnel route dns your-tunnel-id llamaindex.your-domain.com
cloudflared tunnel route dns your-tunnel-id app.your-domain.com
```

### 6. Start Tunnel

```bash
# Start the tunnel
cloudflared tunnel run your-tunnel-id

# Or run as a service (recommended for production)
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

### 7. Verify Tunnel Setup

```bash
# Check tunnel status
cloudflared tunnel list

# Test connectivity
curl https://api.your-domain.com/health/
curl https://llamaindex.your-domain.com/health
```

### 8. Production Service Setup

For production, set up cloudflared as a system service:

```bash
# Create systemd service file
sudo tee /etc/systemd/system/cloudflared.service > /dev/null <<EOF
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=simple
User=cloudflared
ExecStart=/usr/local/bin/cloudflared tunnel --config /home/cloudflared/.cloudflared/config.yml run
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create cloudflared user
sudo useradd -r -s /bin/false cloudflared

# Set permissions
sudo chown -R cloudflared:cloudflared /home/cloudflared/.cloudflared/
sudo chmod 600 /home/cloudflared/.cloudflared/config.yml

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared
```

### 9. Security Configuration

#### Access Policies (Optional)

Create access policies in Cloudflare Zero Trust:

```bash
# Install Cloudflare Wrangler CLI
npm install -g wrangler

# Login to Cloudflare
wrangler login

# Create access application
wrangler tail --name opie-saas
```

#### Firewall Rules

```bash
# Block direct access to your services (only allow Cloudflare IPs)
# This should be done in your cloud provider's firewall settings

# For Google Cloud:
gcloud compute firewall-rules create allow-cloudflare-only \
  --allow tcp:443 \
  --source-ranges 173.245.48.0/20,103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,141.101.64.0/18,108.162.192.0/18,190.93.240.0/20,188.114.96.0/20,197.234.240.0/22,198.41.128.0/17,162.158.0.0/15,104.16.0.0/13,104.24.0.0/14,172.64.0.0/13,131.0.72.0/22 \
  --target-tags cloudflare-tunnel
```

### 10. Monitoring and Logs

```bash
# View tunnel logs
cloudflared tunnel --loglevel debug run your-tunnel-id

# Check service logs
sudo journalctl -u cloudflared -f

# Monitor tunnel health
curl -s https://api.your-domain.com/health/ | jq
```

### 11. Troubleshooting Cloudflare Tunnel

#### Common Issues

```bash
# Check tunnel status
cloudflared tunnel info your-tunnel-id

# Test connectivity
cloudflared tunnel ingress validate

# Check DNS resolution
nslookup api.your-domain.com

# Verify SSL certificates
openssl s_client -connect api.your-domain.com:443 -servername api.your-domain.com
```

#### Debug Mode

```bash
# Run with debug logging
cloudflared tunnel --loglevel debug run your-tunnel-id

# Check configuration
cloudflared tunnel ingress validate --config /path/to/config.yml
```

### 12. Benefits of Cloudflare Tunnel

- **Security**: No need to expose services directly to the internet
- **SSL/TLS**: Automatic HTTPS with Cloudflare's certificates
- **DDoS Protection**: Built-in protection against attacks
- **Performance**: Global CDN and caching
- **Access Control**: Zero Trust policies and authentication
- **Monitoring**: Built-in analytics and logging

## Additional Requirements

### 1. Monitoring and Logging

```bash
# Enable Cloud Monitoring
gcloud services enable monitoring.googleapis.com

# Enable Cloud Logging
gcloud services enable logging.googleapis.com

# Set up alerting policies in Cloud Console
```

### 2. Backup Configuration

```bash
# Enable automated backups (already configured in Terraform)
gcloud sql instances describe db0 --project=bh-opie --format="value(settings.backupConfiguration.enabled)"
```

### 3. Security Hardening

```bash
# Enable Cloud Armor (if needed)
gcloud services enable compute.googleapis.com

# Configure firewall rules
gcloud compute firewall-rules create allow-https \
  --allow tcp:443 \
  --source-ranges 0.0.0.0/0
```

### 4. Performance Optimization

```bash
# Enable Cloud CDN (if needed)
gcloud compute url-maps create cdn-map \
  --default-service=your-backend-service

# Configure Redis for caching
docker-compose -f docker-compose.db.yml up -d redis
```

## Troubleshooting

### Common Issues

#### 1. Cloud SQL Connection Issues

```bash
# Check if proxy is running
docker ps | grep cloudsql-proxy

# Check proxy logs
docker logs reggie_saas-cloudsql-proxy-1

# Verify public IP is assigned
gcloud sql instances describe db0 --project=bh-opie --format="value(ipAddresses[0].ipAddress)"
```

#### 2. Database Migration Issues

```bash
# Check database connection
python manage.py dbshell --settings=bh_opie.settings

# Reset migrations (if needed)
python manage.py migrate --fake-initial
```

#### 3. Cloud Run Deployment Issues

```bash
# Check service status
gcloud run services describe your-service --region=australia-southeast1

# View logs
gcloud logs read --service=your-service --limit=50
```

#### 4. GitHub Actions Issues

```bash
# Verify secrets are set
# Go to GitHub → Settings → Secrets and variables → Actions

# Check service account permissions
gcloud projects get-iam-policy bh-opie --flatten="bindings[].members" --format="table(bindings.role)" --filter="bindings.members:github-actions@bh-opie.iam.gserviceaccount.com"
```

### Getting Help

1. Check the logs: `gcloud logs read --limit=100`
2. Verify IAM permissions: `gcloud projects get-iam-policy bh-opie`
3. Test connectivity: `gcloud sql connect db0 --user=opieuser --project=bh-opie`
4. Review Terraform state: `terraform show`

## Security Considerations

### 1. Secrets Management
- All sensitive data stored in Google Secret Manager
- Service account keys rotated regularly
- No hardcoded credentials in code

### 2. Network Security
- VPC with private IP for Cloud SQL
- Cloud Armor for DDoS protection
- HTTPS enforced everywhere

### 3. Access Control
- Principle of least privilege for IAM roles
- Regular access reviews
- Multi-factor authentication required

## Cost Optimization

### 1. Resource Sizing
- Use appropriate machine types
- Enable auto-scaling
- Monitor resource usage

### 2. Storage Optimization
- Lifecycle policies for logs
- Compression enabled
- Regular cleanup of old data

### 3. Monitoring Costs
- Set up billing alerts
- Regular cost reviews
- Use committed use discounts where applicable

---

## Next Steps

After successful deployment:

1. **Set up monitoring** - Configure alerts and dashboards
2. **Configure backups** - Verify backup policies are working
3. **Security audit** - Review access controls and permissions
4. **Performance testing** - Load test your application
5. **Documentation** - Update team documentation with environment details

For questions or issues, refer to the troubleshooting section or contact the development team.
