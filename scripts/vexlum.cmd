@echo off
REM vexlum: single entry point for Vexlum Scoring (MCP server + CLI).
REM   scripts\vexlum.cmd                 stdio MCP server (search, resolve, execute)
REM   scripts\vexlum.cmd search "..."    CLI; see docs/technical/VEXLUM_MCP.md
REM The Python core runs in image-scoring-gpu-shell; build the host once: cd mcp-server ^&^& npm ci ^&^& npm run build
setlocal
set "ENTRY=%~dp0..\mcp-server\dist\vexlum.js"
if not exist "%ENTRY%" (
    echo vexlum: %ENTRY% not found. Run: cd mcp-server ^&^& npm ci ^&^& npm run build 1>&2
    exit /b 2
)
node "%ENTRY%" %*
exit /b %ERRORLEVEL%
