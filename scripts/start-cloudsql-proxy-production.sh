#!/bin/bash
# Production Cloud SQL Proxy Setup (Google-Blessed)
# Uses private IP + Cloud SQL Auth Proxy v2 + IAM auth
# For VM in same VPC as Cloud SQL

set -eo pipefail

# Configuration
PROJECT_ID=${PROJECT_ID:-bh-opie}
INSTANCE_NAME=${INSTANCE_NAME:-db0}
CONNECTION_NAME="${PROJECT_ID}:australia-southeast1:${INSTANCE_NAME}"
PROXY_PORT=${PROXY_PORT:-5432}
CONTAINER_NAME=${CONTAINER_NAME:-reggie_saas-cloudsql-proxy-1}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Function to check if Cloud SQL instance has private IP
has_private_ip() {
    gcloud sql instances describe "$INSTANCE_NAME" --project="$PROJECT_ID" --format="value(ipAddresses[0].ipAddress)" 2>/dev/null | grep -q "10\."
}

# Function to check if Cloud SQL Auth Proxy is installed
check_cloud_sql_proxy() {
    if command -v cloud-sql-proxy &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# Function to install Cloud SQL Auth Proxy
install_cloud_sql_proxy() {
    print_status "Installing Cloud SQL Auth Proxy v2..."
    
    # Detect architecture
    ARCH=$(uname -m)
    case $ARCH in
        x86_64) ARCH="amd64" ;;
        arm64|aarch64) ARCH="arm64" ;;
        *) print_error "Unsupported architecture: $ARCH"; exit 1 ;;
    esac
    
    # Download and install
    curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.1/cloud-sql-proxy.linux.${ARCH}
    chmod +x cloud-sql-proxy
    sudo mv cloud-sql-proxy /usr/local/bin/
    
    print_status "Cloud SQL Auth Proxy installed successfully"
}

# Function to start Cloud SQL Auth Proxy with IAM auth
start_proxy_iam() {
    print_status "Starting Cloud SQL Auth Proxy with IAM authentication..."
    
    # Check if container is already running
    if docker ps --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
        print_warning "Cloud SQL proxy container is already running. Stopping it first..."
        docker-compose -f docker-compose.cloudsql-proxy.yml down
    fi
    
    # Start the proxy with IAM auth
    cloud-sql-proxy \
        --private-ip \
        --port "$PROXY_PORT" \
        --auto-iam-authn \
        "$CONNECTION_NAME" &
    
    PROXY_PID=$!
    echo $PROXY_PID > /tmp/cloudsql-proxy.pid
    
    # Wait for proxy to be ready
    print_status "Waiting for Cloud SQL Auth Proxy to be ready..."
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if netstat -tlnp 2>/dev/null | grep -q ":$PROXY_PORT "; then
            print_status "Cloud SQL Auth Proxy is ready!"
            return 0
        fi
        
        sleep 2
        ((attempt++))
    done
    
    print_error "Cloud SQL Auth Proxy failed to start within 60 seconds"
    return 1
}

# Function to start Cloud SQL Auth Proxy with service account
start_proxy_sa() {
    print_status "Starting Cloud SQL Auth Proxy with service account authentication..."
    
    # Check if service account key exists
    if [ ! -f ".gcp/creds/bh-opie/cloud-run.json" ]; then
        print_error "Service account key not found at .gcp/creds/bh-opie/cloud-run.json"
        print_info "Please ensure the service account key is available"
        return 1
    fi
    
    # Start the proxy with service account
    GOOGLE_APPLICATION_CREDENTIALS=".gcp/creds/bh-opie/cloud-run.json" \
    cloud-sql-proxy \
        --private-ip \
        --port "$PROXY_PORT" \
        "$CONNECTION_NAME" &
    
    PROXY_PID=$!
    echo $PROXY_PID > /tmp/cloudsql-proxy.pid
    
    # Wait for proxy to be ready
    print_status "Waiting for Cloud SQL Auth Proxy to be ready..."
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if netstat -tlnp 2>/dev/null | grep -q ":$PROXY_PORT "; then
            print_status "Cloud SQL Auth Proxy is ready!"
            return 0
        fi
        sleep 2
        ((attempt++))
    done
    
    print_error "Cloud SQL Auth Proxy failed to start within 60 seconds"
    return 1
}

# Function to stop Cloud SQL Auth Proxy
stop_proxy() {
    print_status "Stopping Cloud SQL Auth Proxy..."
    
    if [ -f "/tmp/cloudsql-proxy.pid" ]; then
        local pid=$(cat /tmp/cloudsql-proxy.pid)
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            print_status "Cloud SQL Auth Proxy stopped"
        fi
        rm -f /tmp/cloudsql-proxy.pid
    fi
}

# Function to test database connection
test_connection() {
    print_status "Testing database connection..."
    
    # Get database credentials from environment or deployment.env
    local db_user=${DB_USER:-opieuser}
    local db_password=${DB_PASSWORD:-}
    local db_name=${DB_NAME:-bh_opie}
    
    if [ -z "$db_password" ]; then
        # Try to get from deployment.env
        if [ -f "deployment.env" ]; then
            # Safely extract DB_PASS from deployment.env
            db_password=$(grep '^DB_PASS=' deployment.env | cut -d'=' -f2- | sed 's/\$//g')
        elif [ -n "$DB_PASS" ]; then
            db_password="$DB_PASS"
        else
            print_error "Database password not found. Set DB_PASS environment variable or ensure deployment.env exists."
            return 1
        fi
    fi
    
    # Test connection
    if PGPASSWORD="$db_password" psql -h localhost -p "$PROXY_PORT" -U "$db_user" -d "$db_name" -c "SELECT version();" >/dev/null 2>&1; then
        print_status "Database connection successful!"
        return 0
    else
        print_error "Database connection failed!"
        return 1
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --start-iam     Start Cloud SQL proxy with IAM authentication (recommended)"
    echo "  --start-sa      Start Cloud SQL proxy with service account authentication"
    echo "  --stop          Stop Cloud SQL proxy"
    echo "  --restart       Restart Cloud SQL proxy"
    echo "  --test          Test database connection"
    echo "  --status        Show current status"
    echo "  --install       Install Cloud SQL Auth Proxy"
    echo "  --help          Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  PROJECT_ID      GCP Project ID (default: bh-opie)"
    echo "  INSTANCE_NAME   Cloud SQL instance name (default: db0)"
    echo "  PROXY_PORT      Local proxy port (default: 5432)"
    echo "  DB_USER         Database username (default: opieuser)"
    echo "  DB_PASSWORD     Database password"
    echo "  DB_NAME         Database name (default: bh_opie)"
    echo ""
    echo "Examples:"
    echo "  $0 --start-iam              # Start with IAM auth (recommended)"
    echo "  $0 --start-sa               # Start with service account"
    echo "  $0 --stop                   # Stop proxy"
    echo "  $0 --test                   # Test connection"
    echo "  DB_PASSWORD=mypass $0 --start-iam  # Start with specific password"
}

# Function to show status
show_status() {
    echo "=== Cloud SQL Proxy Status ==="
    
    # Check if instance has private IP
    if has_private_ip; then
        local private_ip=$(gcloud sql instances describe "$INSTANCE_NAME" --project="$PROJECT_ID" --format="value(ipAddresses[0].ipAddress)")
        echo "Cloud SQL Instance: $INSTANCE_NAME"
        echo "Private IP: $private_ip"
    else
        echo "Cloud SQL Instance: $INSTANCE_NAME"
        echo "Private IP: Not assigned"
    fi
    
    # Check if proxy is running
    if [ -f "/tmp/cloudsql-proxy.pid" ]; then
        local pid=$(cat /tmp/cloudsql-proxy.pid)
        if kill -0 "$pid" 2>/dev/null; then
            echo "Proxy Process: Running (PID: $pid)"
            echo "Proxy Port: $PROXY_PORT"
        else
            echo "Proxy Process: Not running"
        fi
    else
        echo "Proxy Process: Not running"
    fi
}

# Main script logic
main() {
    # Check if gcloud is installed and authenticated
    if ! command -v gcloud &> /dev/null; then
        print_error "gcloud CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check if we're on a GCP VM
    if ! curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/ >/dev/null 2>&1; then
        print_warning "Not running on a GCP VM. IAM authentication may not work."
        print_info "Consider using --start-sa option with service account key."
    fi
    
    case "${1:-}" in
        --start-iam)
            print_status "Starting Cloud SQL proxy with IAM authentication (Google-blessed approach)..."
            
            # Check if Cloud SQL Auth Proxy is installed
            if ! check_cloud_sql_proxy; then
                print_status "Cloud SQL Auth Proxy not found. Installing..."
                install_cloud_sql_proxy
            fi
            
            # Check if instance has private IP
            if ! has_private_ip; then
                print_error "Cloud SQL instance does not have private IP. This script requires private IP setup."
                exit 1
            fi
            
            # Start proxy with IAM auth
            start_proxy_iam || exit 1
            
            # Test connection
            if test_connection; then
                print_status "Cloud SQL proxy is ready and connected!"
                print_info "Connect using: psql -h localhost -p $PROXY_PORT -U opieuser -d bh_opie"
                print_warning "Press Ctrl+C to stop the proxy"
                
                # Keep running until interrupted
                trap 'stop_proxy; exit 0' INT TERM
                while true; do
                    sleep 1
                done
            else
                print_warning "Proxy started but connection test failed. Check logs."
            fi
            ;;
            
        --start-sa)
            print_status "Starting Cloud SQL proxy with service account authentication..."
            
            # Check if Cloud SQL Auth Proxy is installed
            if ! check_cloud_sql_proxy; then
                print_status "Cloud SQL Auth Proxy not found. Installing..."
                install_cloud_sql_proxy
            fi
            
            # Check if instance has private IP
            if ! has_private_ip; then
                print_error "Cloud SQL instance does not have private IP. This script requires private IP setup."
                exit 1
            fi
            
            # Start proxy with service account
            start_proxy_sa || exit 1
            
            # Test connection
            if test_connection; then
                print_status "Cloud SQL proxy is ready and connected!"
                print_info "Connect using: psql -h localhost -p $PROXY_PORT -U opieuser -d bh_opie"
                print_warning "Press Ctrl+C to stop the proxy"
                
                # Keep running until interrupted
                trap 'stop_proxy; exit 0' INT TERM
                while true; do
                    sleep 1
                done
            else
                print_warning "Proxy started but connection test failed. Check logs."
            fi
            ;;
            
        --stop)
            stop_proxy
            ;;
            
        --restart)
            print_status "Restarting Cloud SQL proxy..."
            stop_proxy
            sleep 2
            main --start-iam
            ;;
            
        --test)
            test_connection
            ;;
            
        --status)
            show_status
            ;;
            
        --install)
            install_cloud_sql_proxy
            ;;
            
        --help|help|-h)
            show_usage
            ;;
            
        "")
            # No arguments provided, default to IAM auth
            print_status "No arguments provided. Starting Cloud SQL proxy with IAM authentication..."
            main --start-iam
            ;;
            
        *)
            print_error "Invalid option: ${1:-}"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
