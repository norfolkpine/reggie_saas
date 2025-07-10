# Development Setup Guide

## Prerequisites

- Python 3.12+
- Docker
- Google Cloud SDK
- PostgreSQL 15+ with pgvector extension
- Make

## Initial Setup

### 1. Clone the Repository
```bash
git clone <repository-url>
cd reggie_saas
```

### 2. Python Virtual Environment
```bash
make venv-create
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Database Setup

#### PostgreSQL with pgvector
1. Install PostgreSQL 15+
2. Install pgvector extension:
```bash
# For MacOS with Homebrew
brew install postgresql@15
brew services start postgresql@15

# Install pgvector
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
make install

# Enable extension in PostgreSQL
psql -d your_database_name -c 'CREATE EXTENSION vector;'
```

3. Create database and user:
```sql
CREATE DATABASE reggie_db;
CREATE USER reggie_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE reggie_db TO reggie_user;
```

4. Run migrations:
```bash
python manage.py migrate
```

### 4. Environment Variables

1. Copy example environment files:
```bash
cp .env.example .env
cp cloudrun/bh-reggie-llamaindex-main/env.example cloudrun/bh-reggie-llamaindex-main/.env
```

2. Configure main application environment variables:
```env
DEBUG=True
SECRET_KEY=your_secret_key
DATABASE_URL=postgres://reggie_user:your_password@localhost:5432/reggie_db
GCP_PROJECT_ID=your_project_id
GCP_STORAGE_BUCKET=your_bucket_name
```

3. Configure CloudRun environment variables:
```env
OPENAI_API_KEY=your_openai_key
GCP_PROJECT_ID=your_project_id
GCP_STORAGE_BUCKET=your_bucket_name
DJANGO_API_KEY=your_django_api_key
```

## CloudRun Deployment

### 1. Setup Google Cloud Project

1. Install Google Cloud SDK:
```bash
# MacOS
brew install google-cloud-sdk
```

2. Initialize and authenticate:
```bash
gcloud init
gcloud auth application-default login
```

3. Configure Docker for GCP:
```bash
gcloud auth configure-docker
```

### 2. Deploy CloudRun Service

1. Build and deploy using Make commands:
```bash
# From project root
make gcp-build
make gcp-push
make gcp-deploy
```

2. Verify deployment:
```bash
gcloud run services describe bh-reggie-web --region your-region
```

### 3. Generate API Keys

1. Create CloudRun API key:
```bash
python manage.py create_cloud_run_api_key
```

2. Update the generated API key in CloudRun environment variables:
```bash
gcloud run services update bh-reggie-web \
  --region your-region \
  --update-env-vars DJANGO_API_KEY=your_generated_key
```

## System Management Commands

### Available Management Commands

1. Database Management:
```bash
# Reset database (development only)
python manage.py reset_db

# Run migrations
python manage.py migrate
```

2. Document Processing:
```bash
# Retry failed document ingestions
python manage.py retry_failed_ingestions

# Re-embed documents
python manage.py rembed_documents
```

3. Model and Agent Management:
```bash
# Load model providers
python manage.py load_model_providers

# Toggle model providers
python manage.py toggle_model_providers

# Load agent instructions
python manage.py load_agent_instructions

# Load agent outputs
python manage.py load_agent_outputs
```

4. Storage Management:
```bash
# Check GCS connectivity
python manage.py check_gcs

# Backfill GCS global files
python manage.py backfill_gcs_global_files
```

## Running the Application

1. Start the Django development server:
```bash
make run
```

2. Access the application:
- Web interface: http://localhost:8000
- Admin interface: http://localhost:8000/admin

## Testing

1. Run tests:
```bash
python manage.py test
```

2. Run linting:
```bash
flake8
black .
```

## Common Issues and Solutions

### pgvector Installation
If you encounter issues installing pgvector:
1. Ensure PostgreSQL development files are installed
2. Check PostgreSQL version compatibility
3. Verify PATH includes PostgreSQL binaries

### CloudRun Deployment
Common deployment issues:
1. Check IAM permissions
2. Verify environment variables
3. Check Docker build context
4. Review CloudRun service logs

### API Key Issues
If API key authentication fails:
1. Verify key format and expiration
2. Check environment variable configuration
3. Review CloudRun service configuration

## Security Best Practices

1. API Keys:
   - Rotate keys regularly
   - Use environment variables
   - Never commit keys to version control

2. Database:
   - Use strong passwords
   - Limit network access
   - Regular backups

3. CloudRun:
   - Use latest runtime versions
   - Configure minimum instances
   - Set appropriate memory limits

## Monitoring and Logging

1. CloudRun Monitoring:
   - View logs in Google Cloud Console
   - Set up alerts for errors
   - Monitor resource usage

2. Application Monitoring:
   - Configure Django logging
   - Set up error tracking
   - Monitor database performance

## Next Steps

1. Set up CI/CD pipeline
2. Configure production environment
3. Set up monitoring and alerting
4. Review security configurations
5. Plan backup strategy 

## Docker Optimisation

Here are some useful commands for inspecting files and space usage inside a Docker container:

### 1. List All Images and Their Sizes
```sh
docker images
```

### 2. Run a Shell Inside a Container
```sh
docker run --rm -it <image-name> bash
```

### 3. Check Disk Usage by Directory
Once inside the container shell:
```sh
du -sh /*
```
To check a specific directory (e.g., /code):
```sh
du -sh /code/*
```

### 4. List Files in a Directory
```sh
ls -lh /code
```

### 5. Find Large Files
```sh
find /code -type f -exec du -h {} + | sort -rh | head -20
```

### 6. Exit the Container
```sh
exit
```

These commands help you audit what is taking up space in your Docker images and containers. 