#!/bin/bash

set -e

echo "🚀 Starting Opie SaaS Local Development Environment"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if .env file exists
if [ ! -f .env ]; then
    print_warning ".env file not found! Creating from template..."
    
    cat > .env << 'EOF'
# Django Configuration
DEBUG=True
SECRET_KEY=django-insecure-dev-key-change-in-production
DJANGO_SETTINGS_MODULE=bh_opie.settings.Development

# Database Configuration (Local PostgreSQL)
POSTGRES_DB=bh_opie
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
DATABASE_URL=postgresql://postgres:postgres@db:5432/bh_opie

# Redis Configuration
REDIS_URL=redis://redis:6379/0
REDIS_CACHE_URL=redis://redis:6379/2

# Google Cloud Configuration
GCP_PROJECT_ID=bh-opie
GS_STATIC_BUCKET_NAME=bh-opie-static
GS_MEDIA_BUCKET_NAME=bh-opie-media
GCS_PREFIX=opie-data/global/library/
PGVECTOR_SCHEMA=ai
PGVECTOR_TABLE=kb__vector_table
VAULT_PGVECTOR_TABLE=vault_vector_table

# API Configuration
DJANGO_API_URL=http://localhost:8000
DJANGO_API_KEY=your-django-api-key
SYSTEM_API_KEY=your-system-api-key

# External Services (Will be loaded from GCP Secret Manager)
OPENAI_API_KEY=your-openai-key
Y_PROVIDER_API_KEY=your-y-provider-key
LLAMAINDEX_API_KEY=your-llamaindex-key

# Collaboration Services
COLLABORATION_API_URL=http://localhost:8000
COLLABORATION_BACKEND_BASE_URL=http://localhost:8000
COLLABORATION_SERVER_ORIGIN=http://localhost:8000
COLLABORATION_SERVER_SECRET=your-collaboration-secret
COLLABORATION_WS_URL=ws://localhost:8000

# Docker Configuration
DOCKER_USER=1000:1000

# Development Settings
LOCAL_DEVELOPMENT=true
FORCE_GCP_DETECTION=True
SKIP_COLLECTSTATIC=False
SKIP_DATA_LOADING=False
EOF
    
    print_success "Created .env file with default values"
    print_warning "Please update the .env file with your actual API keys and configuration"
fi

# Check for Google Cloud authentication
print_status "Checking Google Cloud authentication..."

if ! command -v gcloud &> /dev/null; then
    print_warning "Google Cloud SDK not found. Installing..."
    # Install gcloud (macOS)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &> /dev/null; then
            brew install google-cloud-sdk
        else
            print_error "Please install Google Cloud SDK manually: https://cloud.google.com/sdk/docs/install"
            exit 1
        fi
    else
        print_error "Please install Google Cloud SDK manually: https://cloud.google.com/sdk/docs/install"
        exit 1
    fi
fi

# Check if user is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    print_warning "Not authenticated with Google Cloud. Please authenticate..."
    gcloud auth login
    gcloud auth application-default login
fi

# Set the project
print_status "Setting Google Cloud project to bh-opie..."
gcloud config set project bh-opie

# Check if service account key exists
if [ ! -f .gcp/creds/bh-opie/github-actions.json ]; then
    print_warning "Service account key not found at .gcp/creds/bh-opie/github-actions.json"
    print_status "Creating directory structure..."
    mkdir -p .gcp/creds/bh-opie
    
    print_warning "Please download your service account key and place it at:"
    print_warning ".gcp/creds/bh-opie/github-actions.json"
    print_warning ""
    print_warning "You can download it from:"
    print_warning "https://console.cloud.google.com/iam-admin/serviceaccounts?project=bh-opie"
    print_warning ""
    print_warning "Or create a new service account with these roles:"
    print_warning "- Secret Manager Secret Accessor"
    print_warning "- Storage Object Viewer"
    print_warning "- Cloud SQL Client"
    print_warning ""
    read -p "Press Enter to continue without GCP secrets (using local .env values) or Ctrl+C to exit..."
else
    print_success "Service account key found"
fi

# Check for Docker and Docker Compose
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed or not in PATH"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    print_error "docker-compose is not installed or not in PATH"
    exit 1
fi

# Stop any existing containers
print_status "Stopping any existing containers..."
docker-compose -f docker-compose.local-test.yml down --remove-orphans 2>/dev/null || true

# Build and start all services
print_status "Building and starting all services..."
print_status "This may take a few minutes on first run..."

docker-compose -f docker-compose.local-test.yml up --build -d

# Wait for services to be ready
print_status "Waiting for services to be ready..."

# Wait for database
print_status "Waiting for database..."
timeout 60 bash -c 'until docker-compose -f docker-compose.local-test.yml exec -T db pg_isready -U postgres; do sleep 2; done' || {
    print_error "Database failed to start within 60 seconds"
    exit 1
}

# Wait for Redis
print_status "Waiting for Redis..."
timeout 30 bash -c 'until docker-compose -f docker-compose.local-test.yml exec -T redis redis-cli ping; do sleep 2; done' || {
    print_error "Redis failed to start within 30 seconds"
    exit 1
}

# Run database migrations
print_status "Running database migrations..."
print_status "Running djstripe migrations first..."
docker-compose -f docker-compose.local-test.yml exec -T django python manage.py migrate djstripe
print_status "Running all other migrations..."
docker-compose -f docker-compose.local-test.yml exec -T django python manage.py migrate

# Collect static files
print_status "Collecting static files..."
docker-compose -f docker-compose.local-test.yml exec -T django python manage.py collectstatic --noinput

# Create superuser if it doesn't exist
print_status "Creating superuser (if needed)..."
docker-compose -f docker-compose.local-test.yml exec -T django python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin')
    print('Superuser created: admin/admin')
else:
    print('Superuser already exists')
"

# Show service status
print_success "All services are running!"
echo ""
echo "🌐 Service URLs:"
echo "  Django Web App:    http://localhost:8000"
echo "  Django Admin:      http://localhost:8000/admin"
echo "  y-provider API:    http://localhost:4444"
echo "  Llamaindex API:    http://localhost:8080"
echo "  PostgreSQL:        localhost:5432"
echo "  Redis:             localhost:6379"
echo ""
echo "🔑 Default Login:"
echo "  Username: admin"
echo "  Password: admin"
echo ""
echo "📋 Useful Commands:"
echo "  View logs:         docker-compose -f docker-compose.local-test.yml logs -f"
echo "  Stop services:     docker-compose -f docker-compose.local-test.yml down"
echo "  Restart services:  docker-compose -f docker-compose.local-test.yml restart"
echo "  Shell access:      docker-compose -f docker-compose.local-test.yml exec django bash"
echo "  Database shell:    docker-compose -f docker-compose.local-test.yml exec db psql -U postgres -d bh_opie"
echo ""
print_success "Development environment is ready! 🎉"
 terraform