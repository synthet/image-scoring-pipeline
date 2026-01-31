# Docker Setup Guide

This guide describes how to run the Image Scoring application using Docker Desktop for Windows with WSL 2 and GPU acceleration.

## Prerequisites

1.  **Docker Desktop**: Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
2.  **WSL 2 Backend**: Ensure Docker Desktop is configured to use the WSL 2 based engine.
3.  **NVIDIA Container Toolkit**: 
    - Ensure you have the latest NVIDIA drivers on your Windows host.
    - Docker Desktop for Windows supports GPU-PV (GPU Paravirtualization) out of the box with the WSL 2 backend.
4.  **Firebird SQL**: The Firebird service must be running on your Windows host.

## Quick Start

1.  **Start Firebird**: Ensure the Firebird Server service is running on Windows (Port 3050).
2.  **Launch Launcher**: Double-click `run_webui_docker.bat` in the project root.
3.  **Access WebUI**: Once the build and startup are complete, open your browser to:
    `http://localhost:7860`

## Configuration

### Volume Mounts
The `docker-compose.yml` file defaults to mounting the following Windows paths into the container:
- `.` (Project Root) -> `/app`
- `D:/` -> `/mnt/d`
- `E:/` -> `/mnt/e`
- `F:/` -> `/mnt/f`

If your photos are stored on other drives, add them to the `volumes` section of `docker-compose.yml`.

## Visual Overview

```mermaid
graph TD
  User[User] --> WebUI[Gradio WebUI (Docker Container)]

  subgraph WindowsHost["Windows Host"]
    FB_Service[Firebird Server Service]
    Photos[Photo drives (D:/, E:/, ...)]
  end

  subgraph Container["Docker Container"]
    App[Image Scoring App]
    CUDA[CUDA 12.6 + cuDNN]
    App --> CUDA
  end

  WebUI --> App
  App -->|host.docker.internal:3050| FB_Service
  App -->|Volume mounts| Photos
```

### GPU Confirmation
When the container starts, you should see logs from TensorFlow/PyTorch indicating that a GPU (e.g., NVIDIA GeForce RTX ...) has been detected and initialized.

## Troubleshooting

### Firebird Connection Failed
If the container cannot connect to Firebird:
1. Verify Firebird is running on Windows.
2. Ensure Windows Firewall permits incoming connections on port 3050. Run `setup_firewall.bat` as Administrator.
3. Ensure the database path in `modules/db.py` matches your actual Windows path.

### No GPU Detected
1. Verify `nvidia-smi` works in a standard WSL 2 terminal.
2. Check that `deploy.resources.reservations.devices` is present in `docker-compose.yml`.
3. Update NVIDIA drivers to the latest version.

### Slow Performance
Accessing files across the Windows/WSL boundary (e.g., `/mnt/d`) is slower than native Linux filesystems. For maximum performance, consider moving your workspace into the WSL filesystem, though this makes Windows integration more complex.
