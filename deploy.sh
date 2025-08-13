#!/bin/bash

# Ensure we're on main branch
current_branch=$(git branch --show-current)
if [ "$current_branch" != "main" ]; then
    echo "Error: Must be on main branch to deploy"
    exit 1
fi

# Check if there are uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo "Error: You have uncommitted changes. Please commit or stash them first."
    exit 1
fi

# Set git pull strategy to rebase
git config pull.rebase true

# Pull latest changes first
echo "Pulling latest changes..."
git pull origin $current_branch

# Get current version and prompt for new one
current_version=$(git describe --tags --abbrev=0 2>/dev/null || echo "0.0.0")
echo "Current version: $current_version"
read -p "Enter new version (leave blank to skip): " new_version

if [ ! -z "$new_version" ]; then
    # Create and push tag
    git tag "v$new_version"
    git push origin "v$new_version"
fi

# Push to repository
echo "Pushing to repository..."
git push origin $current_branch

echo "Deployment pushed successfully!"
echo "To update the remote Mac Studio, run these commands:"
echo "1. SSH into Mac Studio"
echo "2. cd ~/repos/home-video-cleaner"
echo "3. ./update.sh"