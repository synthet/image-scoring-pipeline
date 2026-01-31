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

REM Navigate to project directory and run the fix script
wsl bash -c "cd /mnt/d/Projects/image-scoring ^&^& chmod +x scripts/fix_nvidia_docker.sh ^&^& ./scripts/fix_nvidia_docker.sh"

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
