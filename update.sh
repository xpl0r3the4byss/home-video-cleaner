#!/bin/bash

# Configuration
BRANCH=${1:-"main"}  # Default to main branch if not specified

# Check Python dependencies
check_dependencies() {
    echo "Checking Python dependencies..."
    
    # Install pip if not present
    if ! command -v pip &> /dev/null; then
        echo "Installing pip..."
        curl -O https://bootstrap.pypa.io/get-pip.py
        python3 get-pip.py --user
        rm get-pip.py
    fi

    # Install required packages
    pip install --user -r requirements.txt
}

# Backup function (in case we add a config file later)
backup_data() {
    echo "Creating backup..."
    mkdir -p backups
    
    # Backup any potential config files
    if [ -f "config.py" ]; then
        cp config.py "backups/config-$(date +%Y%m%d_%H%M%S).py"
    fi
}

# Main update process
main() {
    # First check dependencies
    check_dependencies

    # Backup current data
    backup_data

    # Get current version before update
    current_version=$(git describe --tags --abbrev=0 2>/dev/null || echo "0.0.0")

    # Pull latest changes
    echo "Pulling latest changes..."
    git fetch origin
    git checkout $BRANCH
    git pull origin $BRANCH

    # Get new version
    new_version=$(git describe --tags --abbrev=0 2>/dev/null || echo "0.0.0")

    echo "Updated from version $current_version to $new_version"
    echo "Update completed successfully!"
}

# Run main process
main