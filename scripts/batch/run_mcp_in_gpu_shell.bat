@echo off
REM Run an MCP stdio server inside image-scoring-gpu-shell, the default Python
REM environment for this repo. The run_mcp_*_windows.bat launchers call this when
REM the Windows .venv is absent. stdout carries JSON-RPC, so all other output goes to stderr.
REM Usage: run_mcp_in_gpu_shell.bat <python module>   (honours MCP_TOOL_PROFILE)
setlocal
set "CONTAINER=image-scoring-gpu-shell"

docker start %CONTAINER% >nul 2>&1
if errorlevel 1 (
    echo ERROR: no .venv and could not start %CONTAINER%. Run: docker compose --profile gpu-shell up -d db gpu-shell 1>&2
    exit /b 1
)

docker exec -i -w /app -e PYTHONPATH=/app -e ENABLE_MCP_SERVER=1 -e MCP_TOOL_PROFILE=%MCP_TOOL_PROFILE% %CONTAINER% python -m %1
exit /b %ERRORLEVEL%
