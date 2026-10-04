@echo off
REM Compact MCP stdio (search + dispatch only). No pause — stdio must stay open.
setlocal enabledelayedexpansion

cd /d "%~dp0..\.."
set "PROJECT_ROOT=%CD%"
set ENABLE_MCP_SERVER=1
set MCP_TOOL_PROFILE=compact

if exist "%PROJECT_ROOT%\.venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%\.venv\Scripts\activate.bat"
) else (
    REM No Windows .venv: run the same server in image-scoring-gpu-shell instead.
    call "%~dp0run_mcp_in_gpu_shell.bat" modules.mcp.router_server
    exit /b !ERRORLEVEL!
)

python -m modules.mcp.router_server
