@echo off
REM ============================================================
REM Fix NVIDIA Docker GPU Access - Windows Launcher
REM ============================================================
REM This script launches the GPU fix script in WSL
REM ============================================================

echo ============================================================
echo  NVIDIA Docker GPU Access Fix (WSL)
echo ============================================================
echo [INFO] This will diagnose and fix GPU access in Docker containers
echo [INFO] Transitioning to WSL...
echo.

REM Get project root dynamically
setlocal enabledelayedexpansion
for %%I in ("%~dp0") do set "PROJECT_ROOT=%%~fI"
set "WSL_PATH=!PROJECT_ROOT:\=/!"
set "WSL_PATH=!WSL_PATH::=!"
set "WSL_PATH=/mnt/!WSL_PATH!"
set "WSL_PATH=!WSL_PATH:/mnt/C=/mnt/c!"
set "WSL_PATH=!WSL_PATH:/mnt/D=/mnt/d!"
if "!WSL_PATH:~-1!"=="/" set "WSL_PATH=!WSL_PATH:~0,-1!"

REM Navigate to project directory and run the fix script
wsl bash -c "cd !WSL_PATH! && chmod +x scripts/fix_nvidia_docker.sh && ./scripts/fix_nvidia_docker.sh"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================================
    echo [SUCCESS] GPU access fix completed!
    echo ============================================================
    echo.
    echo You can now run the smoke test again to verify:
    echo   run_docker_smoke_test.bat
    echo.
) else (
    echo.
    echo ============================================================
    echo [ERROR] GPU fix encountered issues
    echo ============================================================
    echo.
    echo Please review the error messages above.
    echo.
)

pause
