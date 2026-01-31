#!/bin/bash
# ============================================================
# NVIDIA Container Toolkit Installation for WSL2
# ============================================================
# This script installs NVIDIA Container Toolkit to enable
# GPU acceleration in Docker containers (CUDA support)
# ============================================================
# Prerequisites:
# - NVIDIA GPU with CUDA support
# - NVIDIA drivers installed on Windows (not in WSL)
# - Docker already installed in WSL2
# ============================================================

set -e

echo "============================================================"
echo " NVIDIA Container Toolkit Installation"
echo "============================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please run install_docker_wsl.sh first."
    exit 1
fi

# Check if running in WSL
if ! grep -qi microsoft /proc/version; then
    print_error "This script is designed for WSL2."
    exit 1
fi

print_info "Detected WSL2 environment"

# Update package index
print_info "Updating package index..."
sudo apt-get update

# Install required packages
print_info "Installing required packages..."
sudo apt-get install -y \
    curl \
    gnupg \
    ca-certificates

# Add NVIDIA Container Toolkit repository
print_info "Adding NVIDIA Container Toolkit repository..."
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

# Use the stable deb repository (distribution-agnostic)
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Update package index
print_info "Updating package index..."
sudo apt-get update

# Install NVIDIA Container Toolkit
print_info "Installing NVIDIA Container Toolkit..."
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker to use NVIDIA runtime
print_info "Configuring Docker to use NVIDIA runtime..."
sudo nvidia-ctk runtime configure --runtime=docker

# Restart Docker
print_info "Restarting Docker service..."
sudo service docker restart

# Verify NVIDIA GPU access
print_info "Verifying NVIDIA GPU access..."
echo ""

if docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi 2>&1 | grep -q "NVIDIA-SMI"; then
    print_info "NVIDIA Container Toolkit installation successful!"
    echo ""
    print_info "GPU is accessible in Docker containers"
    echo ""
    docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi
else
    print_warning "Could not verify GPU access. This might be normal if:"
    print_warning "  - NVIDIA drivers are not installed on Windows"
    print_warning "  - Your system doesn't have an NVIDIA GPU"
    print_warning "  - WSL2 CUDA support is not enabled"
    echo ""
    print_info "You can still use Docker, but GPU acceleration will not be available."
fi

echo ""
print_info "Installation complete!"
echo ""
print_info "To test GPU in your containers, use the --gpus all flag:"
echo "  docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi"
