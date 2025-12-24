@echo off
REM Run MCP Server Standalone for Image Scoring
REM This starts the MCP debugging server that can be connected to from Cursor

cd /d %~dp0\..\..

echo Starting Image Scoring MCP Server...
echo.
echo This server provides debugging tools for Cursor IDE.
echo Available tools: get_database_stats, query_images, execute_sql, etc.
echo.
echo Connect from Cursor using MCP configuration.
echo.

python -m modules.mcp_server

pause

