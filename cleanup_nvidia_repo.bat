@echo off
REM ============================================================
REM Clean up failed NVIDIA repository configuration
REM ============================================================

echo Cleaning up corrupted NVIDIA repository configuration...
wsl bash -c "sudo rm -f /etc/apt/sources.list.d/nvidia-container-toolkit.list"
wsl bash -c "sudo rm -f /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg"

echo Done! You can now run: install_and_verify_docker.bat
pause
