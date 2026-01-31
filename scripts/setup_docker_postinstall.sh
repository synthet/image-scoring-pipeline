#!/bin/bash
# ============================================================
# Docker Post-Installation Setup for WSL2
# ============================================================
# This script performs post-installation configuration:
# - Adds current user to docker group (no sudo needed)
# - Configures Docker to start on WSL boot
# - Sets up Docker daemon for better WSL2 performance
# ============================================================

set -e

echo "============================================================"
echo " Docker Post-Installation Setup"
echo "============================================================"
echo ""

# Colors for output
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

# Add user to docker group
print_info "Adding $USER to docker group..."
sudo usermod -aG docker $USER

# Create Docker daemon configuration for WSL2
print_info "Configuring Docker daemon for WSL2..."
sudo mkdir -p /etc/docker

# Create daemon.json with WSL2-optimized settings
sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2"
}
EOF

# Restart Docker to apply changes
print_info "Restarting Docker service..."
sudo service docker restart

# Create a WSL boot script to auto-start Docker
print_info "Setting up Docker auto-start..."
BOOT_SCRIPT="$HOME/.docker-autostart.sh"

cat > "$BOOT_SCRIPT" <<'EOF'
#!/bin/bash
# Auto-start Docker in WSL2
if ! pgrep -x dockerd > /dev/null; then
    sudo service docker start > /dev/null 2>&1
fi
EOF

chmod +x "$BOOT_SCRIPT"

# Add to .bashrc if not already present
if ! grep -q ".docker-autostart.sh" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# Auto-start Docker" >> ~/.bashrc
    echo "source ~/.docker-autostart.sh" >> ~/.bashrc
    print_info "Added Docker auto-start to .bashrc"
fi

echo ""
print_warning "IMPORTANT: You must log out and log back in (or restart WSL) for group changes to take effect!"
echo ""
echo "To apply changes immediately in this session, run:"
echo "  newgrp docker"
echo ""
print_info "Post-installation setup complete!"
echo ""
echo "Test Docker without sudo:"
echo "  docker run hello-world"
