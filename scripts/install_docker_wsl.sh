#!/bin/bash
# ============================================================
# Docker Installation Script for WSL2 (Ubuntu)
# ============================================================
# This script installs Docker Engine from scratch in WSL2
# Tested on: Ubuntu 22.04 LTS (WSL2)
# ============================================================

set -e  # Exit on any error

echo "============================================================"
echo " Docker WSL2 Installation"
echo "============================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running in WSL
if ! grep -qi microsoft /proc/version; then
    print_error "This script is designed for WSL2. Detected non-WSL environment."
    exit 1
fi

print_info "Detected WSL2 environment"

# Update package index
print_info "Updating package index..."
sudo apt-get update

# Install required packages
print_info "Installing required packages..."
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key
print_info "Adding Docker GPG key..."
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up the Docker repository
print_info "Setting up Docker repository..."
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package index again
print_info "Updating package index with Docker repository..."
sudo apt-get update

# Install Docker Engine, containerd, and Docker Compose
print_info "Installing Docker Engine, containerd, and Docker Compose..."
sudo apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

# Start Docker service
print_info "Starting Docker service..."
sudo service docker start

# Verify Docker is running
if sudo docker run hello-world > /dev/null 2>&1; then
    print_info "Docker installation successful!"
    echo ""
    sudo docker --version
    sudo docker compose version
else
    print_error "Docker installation failed verification"
    exit 1
fi

echo ""
print_warning "Next steps:"
echo "  1. Run the post-installation script: ./scripts/setup_docker_postinstall.sh"
echo "  2. For GPU support, run: ./scripts/install_nvidia_docker.sh"
echo "  3. Restart your terminal or run: source ~/.bashrc"
echo ""
print_info "Installation complete!"
