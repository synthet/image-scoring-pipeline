@echo off
REM ============================================================
REM Docker WSL2 Installation Launcher (Windows)
REM ============================================================
REM This batch file launches the Docker installation process
REM from Windows, executing scripts inside WSL2
REM ============================================================

echo ============================================================
echo  Docker WSL2 Installation Launcher
echo ============================================================
echo.

REM Navigate to project directory in WSL (dynamically detected)
setlocal enabledelayedexpansion
for %%I in ("%~dp0") do set "PROJECT_ROOT=%%~fI"
set "WSL_PROJECT_PATH=!PROJECT_ROOT:\=/!"
set "WSL_PROJECT_PATH=!WSL_PROJECT_PATH::=!"
set "WSL_PROJECT_PATH=/mnt/!WSL_PROJECT_PATH!"
set "WSL_PROJECT_PATH=!WSL_PROJECT_PATH:/mnt/C=/mnt/c!"
set "WSL_PROJECT_PATH=!WSL_PROJECT_PATH:/mnt/D=/mnt/d!"
REM Remove trailing slash if present
if "!WSL_PROJECT_PATH:~-1!"=="/" set "WSL_PROJECT_PATH=!WSL_PROJECT_PATH:~0,-1!"

echo [INFO] Preparing installation scripts...
echo.

REM Make all scripts executable
wsl cd %WSL_PROJECT_PATH% ^&^& chmod +x scripts/install_docker_wsl.sh scripts/setup_docker_postinstall.sh scripts/install_nvidia_docker.sh scripts/verify_docker_wsl.sh

echo.
echo ============================================================
echo  Step 1: Install Docker Engine
echo ============================================================
echo.
echo This will install Docker Engine in your WSL2 Ubuntu environment.
echo.
pause

wsl cd %WSL_PROJECT_PATH% ^&^& ./scripts/install_docker_wsl.sh

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [FAIL] Docker installation failed. Please check the errors above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Step 2: Post-Installation Setup
echo ============================================================
echo.
echo This will configure Docker for non-sudo usage and auto-start.
echo.
pause

wsl cd %WSL_PROJECT_PATH% ^&^& ./scripts/setup_docker_postinstall.sh

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [FAIL] Post-installation setup failed. Please check the errors above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Step 3: Install NVIDIA Container Toolkit (Optional)
echo ============================================================
echo.
echo This enables GPU acceleration in Docker containers.
echo Skip this step if you don't have an NVIDIA GPU.
echo.
set /p INSTALL_NVIDIA="Install NVIDIA Container Toolkit? (y/n): "

if /i "%INSTALL_NVIDIA%"=="y" (
    echo.
    echo [INFO] Installing NVIDIA Container Toolkit...
    wsl cd %WSL_PROJECT_PATH% ^&^& ./scripts/install_nvidia_docker.sh
    
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo [WARN] NVIDIA installation failed or GPU not available.
        echo [INFO] You can still use Docker without GPU support.
        pause
    )
) else (
    echo [INFO] Skipping NVIDIA Container Toolkit installation.
)

echo.
echo ============================================================
echo  Step 4: Restarting WSL
echo ============================================================
echo.
echo To apply all changes, WSL needs to be restarted.
echo This will close all WSL sessions.
echo.
pause

echo [INFO] Shutting down WSL...
wsl --shutdown

timeout /t 3 /nobreak >nul

echo.
echo ============================================================
echo  Step 5: Verifying Installation
echo ============================================================
echo.
echo [INFO] Restarting WSL and verifying Docker installation...
echo.

wsl cd %WSL_PROJECT_PATH% ^&^& ./scripts/verify_docker_wsl.sh

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================================
    echo  Installation Complete!
    echo ============================================================
    echo.
    echo [SUCCESS] Docker is ready to use in WSL2.
    echo.
    echo Next steps:
    echo   1. Run the image-scoring app: .\run_docker.bat
    echo   2. Or manually in WSL: docker compose up
    echo.
) else (
    echo.
    echo [WARN] Some verification checks failed.
    echo Please review the output above and consult docs\DOCKER_WSL2_SETUP.md
    echo.
)

echo.
pause
