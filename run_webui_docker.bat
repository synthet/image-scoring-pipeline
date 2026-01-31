@echo off
setlocal

echo ========================================================
echo   MUSIQ Image Scoring - Docker Launcher
echo ========================================================
echo.

:: Check if Docker is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker Desktop is not running. Please start it first.
    pause
    exit /b 1
)

echo [INFO] Starting containers...
echo [INFO] WebUI will be available at http://localhost:7860
echo.

docker compose up --build

echo.
echo [INFO] Shutdown complete.
pause
