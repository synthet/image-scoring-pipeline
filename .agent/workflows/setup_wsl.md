---
description: Set up the WSL 2 environment for image scoring
---

1. **Install WSL 2**:
   Open PowerShell as Administrator and run:
   ```powershell
   wsl --install
   ```
   *Restart your computer if prompted.*

2. **Install Ubuntu**:
   If not installed by default, install Ubuntu from the Microsoft Store or via terminal:
   ```powershell
   wsl --install -d Ubuntu
   ```

3. **Access Project**:
   WSL automatically mounts Windows drives. Navigate to your project (assuming D: drive):
   ```bash
   cd /path/to/image-scoring
   ```

4. **Install System Dependencies (Inside WSL)**:
   Update `apt` and install Python tools:
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install python3 python3-pip python3-venv -y
   ```

5. **Setup Python Environment (Inside WSL)**:
   Follow the [setup_env](.agent/workflows/setup_env.md) workflow inside the WSL terminal.
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
