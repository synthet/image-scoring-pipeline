@echo off
REM DEPRECATED: use scripts\vexlum.cmd (node mcp-server\dist\vexlum.js). The Python module this starts now serves vexlum (search/resolve/execute); see docs/technical/VEXLUM_MCP.md.
REM Legacy MCP proxy stdio (gpu-shell). Prefer: node mcp-server/dist/compactIndex.js (see .cursor/mcp.example.json).
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0..\powershell\Invoke-GpuShell.ps1' -Env ENABLE_MCP_SERVER=1 -Env MCP_TOOL_PROFILE=compact python -m modules.mcp.proxy_server; exit $LASTEXITCODE"
exit /b %ERRORLEVEL%
