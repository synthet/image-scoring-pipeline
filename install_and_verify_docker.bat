@echo off
REM ============================================================
REM Complete Docker Installation and Verification - Windows
REM ============================================================
REM This script handles the complete Docker setup in WSL:
REM   1. Install Docker Engine
REM   2. Post-installation configuration
REM   3. Install NVIDIA Container Toolkit (for GPU)
REM   4. Verify installation
REM ============================================================

echo ============================================================
echo  Docker Installation and Setup (WSL)
echo ============================================================
echo.
echo This will install Docker in WSL and configure GPU support.
echo You will be prompted for your sudo password.
echo.
pause

REM Get project root dynamically
setlocal enabledelayedexpansion
for %%I in ("%~dp0") do set "PROJECT_ROOT=%%~fI"
set "WSL_PATH=!PROJECT_ROOT:\=/!"
set "WSL_PATH=!WSL_PATH::=!"
set "WSL_PATH=/mnt/!WSL_PATH!"
set "WSL_PATH=!WSL_PATH:/mnt/C=/mnt/c!"
set "WSL_PATH=!WSL_PATH:/mnt/D=/mnt/d!"
if "!WSL_PATH:~-1!"=="/" set "WSL_PATH=!WSL_PATH:~0,-1!"

REM Make all scripts executable
echo [INFO] Making scripts executable...
wsl bash -c "cd !WSL_PATH! && chmod +x scripts/*.sh"

REM Step 1: Install Docker Engine
echo.
echo ============================================================
echo  STEP 1: Installing Docker Engine
echo ============================================================
wsl bash -c "cd !WSL_PATH! && ./scripts/install_docker_wsl.sh"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Docker installation failed!
    pause
    exit /b 1
)

REM Step 2: Post-installation setup
echo.
echo ============================================================
echo  STEP 2: Configuring Docker (sudo-less access)
echo ============================================================
wsl bash -c "cd !WSL_PATH! && ./scripts/setup_docker_postinstall.sh"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARN] Post-installation setup encountered issues
)

REM Step 3: Install NVIDIA Container Toolkit
echo.
echo ============================================================
echo  STEP 3: Installing NVIDIA Container Toolkit (GPU support)
echo ============================================================
wsl bash -c "cd !WSL_PATH! && ./scripts/install_nvidia_docker.sh"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARN] NVIDIA toolkit installation encountered issues
    echo        GPU support may not be available
)

REM Step 4: Restart WSL to apply group changes
echo.
echo ============================================================
echo  STEP 4: Restarting WSL to apply changes...
echo ============================================================
wsl --shutdown
timeout /t 3 /nobreak > nul

REM Step 5: Verify installation
echo.
echo ============================================================
echo  STEP 5: Verifying Docker installation...
echo ============================================================
wsl bash -c "cd !WSL_PATH! && ./scripts/verify_docker_wsl.sh"

echo.
echo ============================================================
echo  Installation Complete!
echo ============================================================
echo.
echo Next steps:
echo   1. Run the smoke test: run_docker_smoke_test.bat
echo   2. Start the application: run_docker.bat
echo.
pause
