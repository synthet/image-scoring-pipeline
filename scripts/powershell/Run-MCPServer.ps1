# Run MCP Server for Image Scoring
# Provides debugging tools for Cursor IDE

param(
  [switch]$Help
)

if ($Help) {
  Write-Host @"
Image Scoring MCP Server
========================

This script starts the MCP (Model Context Protocol) server that provides
debugging tools accessible from Cursor IDE.

Available Tools:
  - get_database_stats    : Database statistics and metrics
  - query_images          : Query images with filters
  - get_image_details     : Get details for specific image
  - execute_sql           : Run read-only SQL queries
  - get_recent_jobs       : Recent job history
  - get_runner_status     : Scoring/tagging runner status
  - get_config            : Read configuration
  - set_config_value      : Update configuration
  - get_folder_tree       : Folder structure with counts
  - get_incomplete_images : Images with missing data
  - read_debug_log        : Recent debug log entries
  - search_images_by_hash : Find image by content hash
  - get_stacks_summary    : Stack/cluster summary

Usage:
  .\Run-MCPServer.ps1       # Start the server
  .\Run-MCPServer.ps1 -Help # Show this help

Configuration:
  Add to Cursor's MCP settings:
  {
    "name": "image-scoring",
    "command": "python",
    "args": ["-m", "modules.mcp_server"],
    "cwd": "/path/to/image-scoring"  // Replace with your project path
  }
"@
  exit 0
}

# Change to project root
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Join-Path $scriptDir "../.." -Resolve
Set-Location $projectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Image Scoring MCP Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Debugging tools for Cursor IDE" -ForegroundColor Yellow
Write-Host "Run with -Help for tool list" -ForegroundColor Yellow
Write-Host ""

# Check if mcp package is installed
$mcpCheck = python -c "import mcp; print('ok')" 2>&1
if ($mcpCheck -ne "ok") {
  Write-Host "Warning: MCP SDK not installed. Installing..." -ForegroundColor Yellow
  pip install mcp
}

# Run the server
python -m modules.mcp_server

