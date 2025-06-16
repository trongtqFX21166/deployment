#!/bin/bash

# Ansible deployment script for Activity API
# Usage: ./deploy.sh [environment] [dry-run]
# Example: ./deploy.sh dev
# Example: ./deploy.sh dev dry-run

set -e

ENVIRONMENT=${1:-dev}
DRY_RUN=${2:-}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANSIBLE_DIR="$SCRIPT_DIR/ansible/$ENVIRONMENT"
INVENTORY_FILE="$ANSIBLE_DIR/inventory.ini"
PLAYBOOK_FILE="$ANSIBLE_DIR/cd.yaml"

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

# Validate environment
validate_environment() {
    if [[ ! "$ENVIRONMENT" =~ ^(dev|prod)$ ]]; then
        print_error "Invalid environment: $ENVIRONMENT. Must be 'dev' or 'prod'"
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if ansible is installed
    if ! command -v ansible-playbook &> /dev/null; then
        print_error "ansible-playbook is not installed. Please install Ansible first."
        exit 1
    fi
    
    # Check if inventory file exists
    if [[ ! -f "$INVENTORY_FILE" ]]; then
        print_error "Inventory file not found: $INVENTORY_FILE"
        exit 1
    fi
    
    # Check if playbook file exists
    if [[ ! -f "$PLAYBOOK_FILE" ]]; then
        print_error "Playbook file not found: $PLAYBOOK_FILE"
        exit 1
    fi
    
    # Check if build config exists
    CONFIG_FILE="$SCRIPT_DIR/app/activity/$ENVIRONMENT/build.config.json"
    if [[ ! -f "$CONFIG_FILE" ]]; then
        print_error "Build config file not found: $CONFIG_FILE"
        exit 1
    fi
    
    print_success "All prerequisites check passed"
}

# Check for applications ready to deploy
check_ready_to_deploy() {
    print_status "Checking for applications ready to deploy..."
    
    CONFIG_FILE="$SCRIPT_DIR/app/activity/$ENVIRONMENT/build.config.json"
    READY_COUNT=$(python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
ready_apps = [app['app'] for app in config if app.get('readytodeploy', 0) == 1]
print(len(ready_apps))
if ready_apps:
    print('Ready to deploy:', ', '.join(ready_apps))
")
    
    if [[ "$READY_COUNT" == "0" ]]; then
        print_warning "No applications are marked as ready to deploy (readytodeploy = 1)"
        print_status "Run the build process first to mark applications for deployment"
        exit 0
    fi
    
    print_success "Found applications ready for deployment"
}

# Run ansible playbook
run_deployment() {
    print_status "Starting deployment to $ENVIRONMENT environment..."
    
    # Prepare ansible command
    ANSIBLE_CMD="ansible-playbook -i $INVENTORY_FILE $PLAYBOOK_FILE"
    
    # Add dry-run flag if specified
    if [[ "$DRY_RUN" == "dry-run" ]]; then
        ANSIBLE_CMD="$ANSIBLE_CMD --check --diff"
        print_warning "Running in DRY-RUN mode - no actual changes will be made"
    fi
    
    # Add verbose output
    ANSIBLE_CMD="$ANSIBLE_CMD -v"
    
    print_status "Executing: $ANSIBLE_CMD"
    
    # Change to the script directory to ensure relative paths work
    cd "$SCRIPT_DIR"
    
    # Run the deployment
    if $ANSIBLE_CMD; then
        if [[ "$DRY_RUN" != "dry-run" ]]; then
            print_success "Deployment completed successfully!"
        else
            print_success "Dry-run completed successfully!"
        fi
    else
        print_error "Deployment failed!"
        exit 1
    fi
}

# Test connectivity to target servers
test_connectivity() {
    print_status "Testing connectivity to target servers..."
    
    if ansible all -i "$INVENTORY_FILE" -m ping; then
        print_success "Connectivity test passed"
    else
        print_error "Connectivity test failed"
        exit 1
    fi
}

# Main function
main() {
    print_status "Starting deployment process for environment: $ENVIRONMENT"
    
    validate_environment
    check_prerequisites
    check_ready_to_deploy
    test_connectivity
    run_deployment
    
    print_success "Deployment process completed!"
}

# Show usage information
show_usage() {
    echo "Usage: $0 [environment] [dry-run]"
    echo ""
    echo "Arguments:"
    echo "  environment  Target environment (dev|prod) [default: dev]"
    echo "  dry-run      Run in dry-run mode (optional)"
    echo ""
    echo "Examples:"
    echo "  $0 dev              # Deploy to dev environment"
    echo "  $0 dev dry-run      # Dry-run deployment to dev environment"
    echo "  $0 prod             # Deploy to prod environment"
    echo ""
}

# Handle help flag
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    show_usage
    exit 0
fi

# Run main function
main