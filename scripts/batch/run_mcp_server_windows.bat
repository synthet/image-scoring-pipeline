@echo off
REM Standalone MCP stdio for Cursor (Windows .venv). No pause — stdio must stay open.
setlocal enabledelayedexpansion

cd /d "%~dp0..\.."
set "PROJECT_ROOT=%CD%"
set "PATH=%PROJECT_ROOT%\Firebird;%PATH%"
set ENABLE_MCP_SERVER=1

if exist "%PROJECT_ROOT%\.venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%\.venv\Scripts\activate.bat"
) else (
    REM No Windows .venv: run the same server in image-scoring-gpu-shell instead.
    call "%~dp0run_mcp_in_gpu_shell.bat" modules.mcp_server
    exit /b !ERRORLEVEL!
)

python -m modules.mcp_server
