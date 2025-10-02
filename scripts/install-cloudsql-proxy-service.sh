#!/bin/bash
# This script installs the Cloud SQL proxy as a systemd service on a production VM
# It creates a systemd service that runs the Cloud SQL Auth Proxy with IAM authentication

# Configuration
SERVICE_NAME="cloudsql-proxy"
SERVICE_USER="cloudsql-proxy"
SERVICE_GROUP="cloudsql-proxy"
INSTALL_DIR="/opt/cloudsql-proxy"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_status() {
    echo -e "${GREEN}[STATUS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Create service user
create_service_user() {
    if ! id "$SERVICE_USER" &>/dev/null; then
        print_status "Creating service user: $SERVICE_USER"
        useradd --system --no-create-home --shell /bin/false "$SERVICE_USER"
        if [ $? -eq 0 ]; then
            print_status "Service user created successfully"
        else
            print_error "Failed to create service user"
            exit 1
        fi
    else
        print_status "Service user already exists"
    fi
}

# Install Cloud SQL Auth Proxy
install_proxy() {
    if [ ! -f "$INSTALL_DIR/cloud-sql-proxy" ]; then
        print_status "Installing Cloud SQL Auth Proxy to $INSTALL_DIR"
        mkdir -p "$INSTALL_DIR"
        
        # Download the latest version
        PROXY_VERSION="2.8.1"
        PROXY_URL="https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v${PROXY_VERSION}/cloud-sql-proxy.linux.amd64"
        
        print_info "Downloading Cloud SQL Auth Proxy v${PROXY_VERSION}..."
        curl -L -o "$INSTALL_DIR/cloud-sql-proxy" "$PROXY_URL"
        
        if [ $? -eq 0 ]; then
            chmod +x "$INSTALL_DIR/cloud-sql-proxy"
            chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/cloud-sql-proxy"
            print_status "Cloud SQL Auth Proxy installed successfully"
        else
            print_error "Failed to download Cloud SQL Auth Proxy"
            exit 1
        fi
    else
        print_status "Cloud SQL Auth Proxy already installed"
    fi
}

# Create systemd service file
create_systemd_service() {
    print_status "Creating systemd service file: $SERVICE_FILE"
    
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Cloud SQL Auth Proxy
Documentation=https://cloud.google.com/sql/docs/mysql/connect-auth-proxy
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
ExecStart=$INSTALL_DIR/cloud-sql-proxy \\
    --ip-addresses=PRIVATE \\
    --port 5432 \\
    --auto-iam-authn \\
    bh-opie:australia-southeast1:db0
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cloudsql-proxy

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR

# Environment
Environment=GOOGLE_APPLICATION_CREDENTIALS=/opt/cloudsql-proxy/credentials.json

[Install]
WantedBy=multi-user.target
EOF

    if [ $? -eq 0 ]; then
        print_status "Systemd service file created successfully"
    else
        print_error "Failed to create systemd service file"
        exit 1
    fi
}

# Set up credentials
setup_credentials() {
    CREDENTIALS_FILE="$INSTALL_DIR/credentials.json"
    
    if [ ! -f "$CREDENTIALS_FILE" ]; then
        print_warning "Service account credentials not found at $CREDENTIALS_FILE"
        print_info "You need to place your service account key file at: $CREDENTIALS_FILE"
        print_info "You can copy it from your deployment:"
        print_info "  sudo cp /path/to/your/service-account-key.json $CREDENTIALS_FILE"
        print_info "  sudo chown $SERVICE_USER:$SERVICE_GROUP $CREDENTIALS_FILE"
        print_info "  sudo chmod 600 $CREDENTIALS_FILE"
        print_warning "The service will not start without proper credentials"
    else
        print_status "Credentials file found"
        chown "$SERVICE_USER:$SERVICE_GROUP" "$CREDENTIALS_FILE"
        chmod 600 "$CREDENTIALS_FILE"
    fi
}

# Reload systemd and enable service
enable_service() {
    print_status "Reloading systemd daemon..."
    systemctl daemon-reload
    
    print_status "Enabling $SERVICE_NAME service..."
    systemctl enable "$SERVICE_NAME"
    
    if [ $? -eq 0 ]; then
        print_status "Service enabled successfully"
        print_info "To start the service: sudo systemctl start $SERVICE_NAME"
        print_info "To check status: sudo systemctl status $SERVICE_NAME"
        print_info "To view logs: sudo journalctl -u $SERVICE_NAME -f"
    else
        print_error "Failed to enable service"
        exit 1
    fi
}

# Show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --install     Install Cloud SQL proxy as systemd service"
    echo "  --uninstall   Remove Cloud SQL proxy service"
    echo "  --start       Start the service"
    echo "  --stop        Stop the service"
    echo "  --restart     Restart the service"
    echo "  --status      Show service status"
    echo "  --logs        Show service logs"
    echo "  --help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  sudo $0 --install    # Install the service"
    echo "  sudo $0 --start      # Start the service"
    echo "  sudo $0 --status     # Check service status"
}

# Uninstall service
uninstall_service() {
    print_status "Stopping and disabling $SERVICE_NAME service..."
    systemctl stop "$SERVICE_NAME" 2>/dev/null
    systemctl disable "$SERVICE_NAME" 2>/dev/null
    
    print_status "Removing systemd service file..."
    rm -f "$SERVICE_FILE"
    
    print_status "Reloading systemd daemon..."
    systemctl daemon-reload
    
    print_status "Service uninstalled successfully"
}

# Service management functions
start_service() {
    systemctl start "$SERVICE_NAME"
    if [ $? -eq 0 ]; then
        print_status "Service started successfully"
    else
        print_error "Failed to start service"
        exit 1
    fi
}

stop_service() {
    systemctl stop "$SERVICE_NAME"
    if [ $? -eq 0 ]; then
        print_status "Service stopped successfully"
    else
        print_error "Failed to stop service"
        exit 1
    fi
}

restart_service() {
    systemctl restart "$SERVICE_NAME"
    if [ $? -eq 0 ]; then
        print_status "Service restarted successfully"
    else
        print_error "Failed to restart service"
        exit 1
    fi
}

show_status() {
    systemctl status "$SERVICE_NAME"
}

show_logs() {
    journalctl -u "$SERVICE_NAME" -f
}

# Main logic
main() {
    local command="${1:-}"
    case "$command" in
        --install)
            check_root
            create_service_user
            install_proxy
            create_systemd_service
            setup_credentials
            enable_service
            print_status "Installation complete!"
            print_info "Next steps:"
            print_info "1. Copy your service account key to $INSTALL_DIR/credentials.json"
            print_info "2. Start the service: sudo systemctl start $SERVICE_NAME"
            print_info "3. Check status: sudo systemctl status $SERVICE_NAME"
            ;;
        --uninstall)
            check_root
            uninstall_service
            ;;
        --start)
            check_root
            start_service
            ;;
        --stop)
            check_root
            stop_service
            ;;
        --restart)
            check_root
            restart_service
            ;;
        --status)
            show_status
            ;;
        --logs)
            show_logs
            ;;
        --help|help|-h)
            show_usage
            ;;
        *)
            print_error "Invalid option: ${1:-}"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

# Execute main function
main "$@"
