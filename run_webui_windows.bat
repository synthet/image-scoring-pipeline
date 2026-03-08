@echo off
setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

REM Add Firebird to PATH for fbclient.dll
set "PATH=%PROJECT_ROOT%\Firebird;%PATH%"

REM Enable MCP server (match WSL default)
set ENABLE_MCP_SERVER=1

REM Activate Windows venv
if exist "%PROJECT_ROOT%\.venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%\.venv\Scripts\activate.bat"
) else (
    echo ERROR: .venv not found. Run scripts\setup\setup_windows_native.bat first.
    pause
    exit /b 1
)

REM launch.py handles Firebird server startup on Windows
cd /d "%PROJECT_ROOT%"
python launch.py %*
pause
