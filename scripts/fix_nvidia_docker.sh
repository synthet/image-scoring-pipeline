#!/bin/bash
# ============================================================
# NVIDIA Docker GPU Access Fix Script
# ============================================================
# This script diagnoses and fixes GPU access issues in Docker
# Specifically addresses NVIDIA Container Toolkit configuration
# ============================================================

set -e

echo "============================================================"
echo " NVIDIA Docker GPU Access Diagnostic & Fix"
echo "============================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_check() {
    echo -e "${BLUE}[CHECK]${NC} $1"
}

# Step 1: Verify prerequisites
print_check "Verifying prerequisites..."
echo ""

# Check nvidia-smi
if command -v nvidia-smi &> /dev/null; then
    print_info "nvidia-smi is available"
    nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
else
    print_error "nvidia-smi not found. NVIDIA drivers may not be properly installed."
    exit 1
fi
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed."
    exit 1
fi
print_info "Docker is installed: $(docker --version)"
echo ""

# Step 2: Check if NVIDIA Container Toolkit is installed
print_check "Checking NVIDIA Container Toolkit..."
if command -v nvidia-ctk &> /dev/null; then
    print_info "NVIDIA Container Toolkit is installed"
    nvidia-ctk --version
else
    print_warning "NVIDIA Container Toolkit is NOT installed"
    print_info "Installing NVIDIA Container Toolkit..."
    
    # Install NVIDIA Container Toolkit
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    
    # Use the stable deb repository (distribution-agnostic)
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    
    sudo apt-get update
    sudo apt-get install -y nvidia-container-toolkit
    
    print_info "NVIDIA Container Toolkit installed"
fi
echo ""

# Step 3: Check Docker daemon configuration
print_check "Checking Docker daemon configuration..."
if [ -f /etc/docker/daemon.json ]; then
    print_info "Current daemon.json:"
    cat /etc/docker/daemon.json
else
    print_warning "No daemon.json found"
fi
echo ""

# Step 4: Configure NVIDIA runtime
print_info "Configuring NVIDIA runtime for Docker..."
sudo nvidia-ctk runtime configure --runtime=docker

echo ""
print_info "Updated daemon.json:"
cat /etc/docker/daemon.json
echo ""

# Step 5: Restart Docker
print_info "Restarting Docker service..."
sudo service docker restart

# Wait for Docker to be ready
sleep 3

# Step 6: Verify Docker is running
if ! sudo service docker status | grep -q "running"; then
    print_error "Docker failed to restart"
    exit 1
fi
print_info "Docker is running"
echo ""

# Step 7: Test GPU access in container
print_check "Testing GPU access in container..."
echo ""

if docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi 2>&1 | grep -q "NVIDIA-SMI"; then
    print_info "SUCCESS! GPU is now accessible in Docker containers!"
    echo ""
    docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi
else
    print_error "GPU access test failed"
    echo ""
    print_info "Attempting diagnostic run..."
    docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi 2>&1 || true
    echo ""
    print_warning "If you see 'could not select device driver', you may need to:"
    print_warning "  1. Ensure NVIDIA drivers are installed on Windows"
    print_warning "  2. Restart WSL: wsl --shutdown (from Windows)"
    print_warning "  3. Re-run this script"
    exit 1
fi

echo ""
echo "============================================================"
print_info "GPU acceleration is now enabled for Docker!"
echo "============================================================"
