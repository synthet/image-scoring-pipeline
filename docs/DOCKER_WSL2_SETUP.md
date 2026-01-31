# Docker WSL2 Setup Guide

This guide provides step-by-step instructions for installing and configuring Docker in WSL2 from scratch.

## Prerequisites

- Windows 10/11 with WSL2 enabled
- Ubuntu distribution installed in WSL2
- At least 10GB of free disk space
- (Optional) NVIDIA GPU for hardware acceleration

## Installation Steps

### Quick Installation (Recommended)

Run the all-in-one installer from Windows:

```cmd
install_and_verify_docker.bat
```

This will:
1. Install Docker Engine in WSL
2. Configure sudo-less access
3. Install NVIDIA Container Toolkit for GPU support
4. Restart WSL and verify everything works

You'll be prompted for your sudo password during installation.

### Manual Installation (Alternative)

If you prefer to run each step manually:

#### Step 1: Install Docker Engine

```bash
cd /path/to/image-scoring
chmod +x scripts/install_docker_wsl.sh
./scripts/install_docker_wsl.sh
```

#### Step 2: Post-Installation Configuration

```bash
chmod +x scripts/setup_docker_postinstall.sh
./scripts/setup_docker_postinstall.sh
```

**Then restart WSL:**
```powershell
# From Windows PowerShell
wsl --shutdown
```

#### Step 3: Install NVIDIA Container Toolkit (GPU support)

```bash
chmod +x scripts/install_nvidia_docker.sh
./scripts/install_nvidia_docker.sh
```

> **Note:** Requires NVIDIA drivers installed on Windows (version 470+)

#### Step 4: Verify Installation

```bash
chmod +x scripts/verify_docker_wsl.sh
./scripts/verify_docker_wsl.sh
```

This will check:
- âœ… WSL2 environment
- âœ… Docker installation
- âœ… Docker service status
- âœ… Non-sudo Docker access
- âœ… Container functionality
- âœ… Docker Compose
- âœ… GPU access (if NVIDIA toolkit installed)
- âœ… Disk space

## Quick Start

After successful installation, test Docker:

```bash
# Basic test
docker run hello-world

# Test GPU (if NVIDIA toolkit installed)
docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi

# Run image-scoring with Docker Compose
docker compose up
```

## Troubleshooting

### Docker service not starting

```bash
sudo service docker start
```

### Permission denied when running Docker

Make sure you've completed Step 2 and restarted WSL or run `newgrp docker`.

### Cannot connect to Docker daemon

```bash
# Check service status
sudo service docker status

# Restart service
sudo service docker restart
```

### GPU not accessible in Docker containers

If the smoke test shows that GPU is not accessible from within containers:

**Quick Fix:**
```cmd
# Clean up any corrupted configuration first
cleanup_nvidia_repo.bat

# Then run the fix
fix_nvidia_docker.bat
```

Or from WSL:
```bash
cd /path/to/image-scoring
# Clean up
sudo rm -f /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo rm -f /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
# Run fix
./scripts/fix_nvidia_docker.sh
```

The fix script will:
1. Verify NVIDIA Container Toolkit is installed (install if missing)
2. Use the correct stable repository URL
3. Configure Docker daemon for NVIDIA runtime
4. Restart Docker service
5. Test GPU access

**If nvidia-smi doesn't work in WSL:**
- Update NVIDIA drivers on Windows to version 470+ (for WSL CUDA support)
- Ensure WSL2 is up to date: `wsl --update` (from Windows PowerShell)
- Verify `nvidia-smi` works in WSL before proceeding


### Docker auto-start not working

Add this to your `~/.bashrc`:

```bash
# Auto-start Docker
if ! pgrep -x dockerd > /dev/null; then
    sudo service docker start > /dev/null 2>&1
fi
```

## Running the Image Scoring Application

Once Docker is installed, you can use the existing Docker workflow:

```bash
# From Windows (PowerShell)
.\run_docker.bat

# Or from WSL
docker compose up
```

See the main [README.md](../README.md) for more details on running the application.

## Uninstalling Docker

If you need to remove Docker:

```bash
# Stop Docker
sudo service docker stop

# Remove Docker packages
sudo apt-get purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Remove Docker data
sudo rm -rf /var/lib/docker
sudo rm -rf /etc/docker

# Remove NVIDIA toolkit (if installed)
sudo apt-get purge -y nvidia-container-toolkit

# Remove Docker group
sudo groupdel docker
```

## Next Steps

- Review [docker-compose.yml](../docker-compose.yml) for configuration options
- Read [DOCKER_SETUP.md](DOCKER_SETUP.md) for advanced Docker usage
- Check [README.md](../README.md) for application-specific documentation
