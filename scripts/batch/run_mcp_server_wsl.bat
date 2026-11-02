@echo off
REM DEPRECATED: use scripts\vexlum.cmd (node mcp-server\dist\vexlum.js). The Python module this starts now serves vexlum (search/resolve/execute); see docs/technical/VEXLUM_MCP.md.
REM Standalone MCP stdio for Cursor (gpu-shell). No pause — stdio must stay open.
REM Prefer node mcp-server/dist/compactIndex.js (see .cursor/mcp.example.json).
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0..\powershell\Invoke-GpuShell.ps1' -Env ENABLE_MCP_SERVER=1 python -m modules.mcp_server; exit $LASTEXITCODE"
exit /b %ERRORLEVEL%
