#!/bin/bash
# Cloud SQL Proxy with Temporary Public IP
# This script temporarily enables public IP for Cloud SQL, starts the proxy, and disables it when done

set -euo pipefail

# Configuration
PROJECT_ID=${PROJECT_ID:-bh-opie}
INSTANCE_NAME=${INSTANCE_NAME:-db0}
PROXY_PORT=${PROXY_PORT:-5432}
CONTAINER_NAME=${CONTAINER_NAME:-reggie_saas-cloudsql-proxy-1}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Function to check if Cloud SQL instance has public IP
has_public_ip() {
    gcloud sql instances describe "$INSTANCE_NAME" --project="$PROJECT_ID" --format="value(ipAddresses[0].ipAddress)" 2>/dev/null | grep -q "."
}

# Function to enable public IP
enable_public_ip() {
    print_status "Enabling public IP for Cloud SQL instance $INSTANCE_NAME..."
    gcloud sql instances patch "$INSTANCE_NAME" --project="$PROJECT_ID" --assign-ip --quiet
    
    # Wait for IP assignment
    print_status "Waiting for public IP assignment..."
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if has_public_ip; then
            local public_ip=$(gcloud sql instances describe "$INSTANCE_NAME" --project="$PROJECT_ID" --format="value(ipAddresses[0].ipAddress)")
            print_status "Public IP assigned: $public_ip"
            return 0
        fi
        sleep 2
        ((attempt++))
    done
    
    print_error "Failed to assign public IP within 60 seconds"
    return 1
}

# Function to disable public IP
disable_public_ip() {
    print_status "Disabling public IP for Cloud SQL instance $INSTANCE_NAME..."
    gcloud sql instances patch "$INSTANCE_NAME" --project="$PROJECT_ID" --no-assign-ip --quiet
    
    # Wait for IP removal
    print_status "Waiting for public IP removal..."
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if ! has_public_ip; then
            print_status "Public IP removed successfully"
            return 0
        fi
        sleep 2
        ((attempt++))
    done
    
    print_warning "Public IP may still be assigned. Check manually with: gcloud sql instances describe $INSTANCE_NAME --project=$PROJECT_ID"
}

# Function to start Cloud SQL proxy
start_proxy() {
    print_status "Starting Cloud SQL proxy..."
    
    # Check if container is already running
    if docker ps --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
        print_warning "Cloud SQL proxy container is already running. Stopping it first..."
        docker-compose -f docker-compose.cloudsql-proxy.yml down
    fi
    
    # Start the proxy
    docker-compose -f docker-compose.cloudsql-proxy.yml up -d
    
    # Wait for proxy to be ready
    print_status "Waiting for Cloud SQL proxy to be ready..."
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if docker logs "$CONTAINER_NAME" 2>&1 | grep -q "The proxy has started successfully"; then
            print_status "Cloud SQL proxy is ready!"
            return 0
        fi
        sleep 2
        ((attempt++))
    done
    
    print_error "Cloud SQL proxy failed to start within 60 seconds"
    return 1
}

# Function to stop Cloud SQL proxy
stop_proxy() {
    print_status "Stopping Cloud SQL proxy..."
    docker-compose -f docker-compose.cloudsql-proxy.yml down
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
            source deployment.env
            db_password="$DB_PASS"
        else
            print_error "Database password not found. Set DB_PASSWORD environment variable or ensure deployment.env exists."
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
    echo "  --start     Start Cloud SQL proxy with temporary public IP"
    echo "  --stop      Stop Cloud SQL proxy and disable public IP"
    echo "  --restart   Restart Cloud SQL proxy (stop + start)"
    echo "  --test      Test database connection"
    echo "  --status    Show current status"
    echo "  --help      Show this help message"
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
    echo "  $0 --start                    # Start proxy with temp public IP"
    echo "  $0 --stop                     # Stop proxy and disable public IP"
    echo "  $0 --restart                  # Restart proxy"
    echo "  $0 --test                     # Test connection"
    echo "  DB_PASSWORD=mypass $0 --start # Start with specific password"
}

# Function to show status
show_status() {
    echo "=== Cloud SQL Proxy Status ==="
    
    # Check if instance has public IP
    if has_public_ip; then
        local public_ip=$(gcloud sql instances describe "$INSTANCE_NAME" --project="$PROJECT_ID" --format="value(ipAddresses[0].ipAddress)")
        echo "Cloud SQL Instance: $INSTANCE_NAME"
        echo "Public IP: $public_ip"
    else
        echo "Cloud SQL Instance: $INSTANCE_NAME"
        echo "Public IP: Not assigned"
    fi
    
    # Check if proxy container is running
    if docker ps --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
        echo "Proxy Container: Running"
        echo "Proxy Port: $PROXY_PORT"
    else
        echo "Proxy Container: Not running"
    fi
}

# Main script logic
main() {
    # Check if gcloud is installed and authenticated
    if ! command -v gcloud &> /dev/null; then
        print_error "gcloud CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check if docker is running
    if ! docker info &> /dev/null; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    
    # Check if docker-compose.cloudsql-proxy.yml exists
    if [ ! -f "docker-compose.cloudsql-proxy.yml" ]; then
        print_error "docker-compose.cloudsql-proxy.yml not found. Please run this script from the project root."
        exit 1
    fi
    
    case "${1:-}" in
        --start)
            print_status "Starting Cloud SQL proxy with temporary public IP..."
            
            # Enable public IP
            enable_public_ip || exit 1
            
            # Start proxy
            start_proxy || {
                print_error "Failed to start proxy. Disabling public IP..."
                disable_public_ip
                exit 1
            }
            
            # Test connection
            if test_connection; then
                print_status "Cloud SQL proxy is ready and connected!"
                print_warning "Remember to run '$0 --stop' when you're done to disable public IP."
            else
                print_warning "Proxy started but connection test failed. Check logs with: docker logs $CONTAINER_NAME"
            fi
            ;;
            
        --stop)
            print_status "Stopping Cloud SQL proxy and disabling public IP..."
            
            # Stop proxy
            stop_proxy
            
            # Disable public IP
            disable_public_ip
            
            print_status "Cloud SQL proxy stopped and public IP disabled."
            ;;
            
        --restart)
            print_status "Restarting Cloud SQL proxy..."
            "$0" --stop
            sleep 2
            "$0" --start
            ;;
            
        --test)
            test_connection
            ;;
            
        --status)
            show_status
            ;;
            
        --help|help|-h)
            show_usage
            ;;
            
        "")
            # No arguments provided, default to --start
            print_status "No arguments provided. Starting Cloud SQL proxy with temporary public IP..."
            main --start
            ;;
            
        *)
            print_error "Invalid option: ${1:-}"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

# Trap to ensure cleanup on script exit
cleanup() {
    if [ "${CLEANUP_ON_EXIT:-false}" = "true" ]; then
        print_warning "Script interrupted. Cleaning up..."
        "$0" --stop
    fi
}

trap cleanup EXIT INT TERM

# Run main function
main "$@"
