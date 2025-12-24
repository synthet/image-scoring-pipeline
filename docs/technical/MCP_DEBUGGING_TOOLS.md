# MCP Debugging Tools for Cursor

This document describes the MCP (Model Context Protocol) server integration that provides remote debugging tools for Cursor IDE.

## Overview

The MCP server exposes a set of tools that allow Cursor to interact with the Image Scoring application:
- Query and analyze the SQLite database
- Monitor scoring/tagging job progress
- Read debug logs
- Manage configuration

## Installation

1. Install the MCP SDK:
```bash
pip install mcp
```

2. Configure Cursor to use the MCP server (see Configuration section below)

## Configuration

### Option 1: Cursor Settings (Recommended)

Add the following to your Cursor MCP settings (Settings → MCP → Add Server):

```json
{
  "name": "image-scoring",
  "command": "python",
  "args": ["-m", "modules.mcp_server"],
  "cwd": "d:\\Projects\\image-scoring"
}
```

### Option 2: Project Config File

Copy the `mcp_config.json` from the project root to your Cursor config directory:
- Windows: `%APPDATA%\Cursor\User\globalStorage\cursor.mcp\mcp.json`
- Or merge its contents into your existing MCP configuration

### Option 3: Running with WebUI

Set the environment variable to enable MCP alongside the WebUI:

```bash
# Windows PowerShell
$env:ENABLE_MCP_SERVER = "1"
python webui.py

# Linux/WSL
ENABLE_MCP_SERVER=1 python webui.py
```

## Available Tools

### Database Tools

#### `get_database_stats`
Get comprehensive database statistics including:
- Total image count
- Distribution by rating and label
- Score distribution histogram
- Average scores per model
- Folder and stack counts
- Today's activity

**Example Output:**
```json
{
  "total_images": 15234,
  "by_rating": {"0": 5000, "1": 100, "2": 500, "3": 3000, "4": 5000, "5": 1634},
  "average_scores": {"general": 0.68, "technical": 0.72, "aesthetic": 0.65}
}
```

#### `query_images`
Query images with flexible filtering:
- `limit` / `offset` - Pagination
- `sort_by` - Sort column (created_at, score_general, etc.)
- `order` - asc/desc
- `min_score` / `max_score` - Score range filter
- `rating` - Filter by rating (0-5)
- `label` - Filter by color label
- `keyword` - Keyword search
- `folder_path` - Filter by folder

**Example:**
```
query_images(limit=10, min_score=0.8, sort_by="score_general", order="desc")
```

#### `get_image_details`
Get full details for a specific image by file path.

**Parameters:**
- `file_path` - Full path to the image

#### `execute_sql`
Execute a read-only SQL SELECT query. Only SELECT queries are allowed for safety.

**Parameters:**
- `query` - SQL SELECT statement
- `params` - Optional query parameters

**Example:**
```sql
SELECT file_name, score_general, rating 
FROM images 
WHERE score_general > 0.8 
ORDER BY score_general DESC 
LIMIT 10
```

#### `search_images_by_hash`
Search for an image by its SHA256 content hash.

**Parameters:**
- `image_hash` - SHA256 hash of image content

### Job & Runner Tools

#### `get_recent_jobs`
Get recent scoring/tagging jobs with status.

**Parameters:**
- `limit` - Number of jobs to return (default: 10)

#### `get_runner_status`
Get current status of background runners including:
- Whether scoring/tagging is running
- Progress (current/total)
- Recent log output

### Configuration Tools

#### `get_config`
Get current application configuration from config.json.

#### `set_config_value`
Set a configuration value.

**Parameters:**
- `key` - Configuration key
- `value` - Value to set (any JSON-compatible type)

### Analysis Tools

#### `get_folder_tree`
Get folder tree structure with image counts per folder.

**Parameters:**
- `root_path` - Optional root path to filter

#### `get_incomplete_images`
Get images with missing or incomplete data (scores, ratings, labels).

**Parameters:**
- `limit` - Max results (default: 50)

#### `get_stacks_summary`
Get summary of image stacks/clusters including:
- Total stacks
- Size distribution
- Largest stacks
- Unstacked image count

**Parameters:**
- `folder_path` - Optional folder filter

#### `read_debug_log`
Read recent entries from the debug log file.

**Parameters:**
- `lines` - Number of lines to read (default: 100)

## Usage Examples

### From Cursor Chat

Once configured, you can ask Cursor to use these tools:

> "Show me database statistics for my image collection"

> "Find all images with score above 0.9"

> "What's the status of the current scoring job?"

> "Show me images that are missing LIQE scores"

> "Get details for the image at D:\Photos\sunset.jpg"

### Debugging Workflow

1. **Check overall health:**
   - Use `get_database_stats` to see image distribution
   - Use `get_incomplete_images` to find problematic records

2. **Monitor running jobs:**
   - Use `get_runner_status` to check progress
   - Use `get_recent_jobs` to see job history

3. **Investigate specific issues:**
   - Use `read_debug_log` to see recent debug entries
   - Use `execute_sql` for custom queries

4. **Analyze data:**
   - Use `query_images` with filters to find patterns
   - Use `get_stacks_summary` to check clustering results

## Security Notes

- The `execute_sql` tool only allows SELECT queries
- Dangerous SQL patterns (DROP, DELETE, etc.) are blocked
- The server runs locally and doesn't expose network endpoints
- Configuration changes are persisted to config.json

## Troubleshooting

### MCP Server Not Starting

1. Verify MCP SDK is installed:
   ```bash
   pip show mcp
   ```

2. Test the server standalone:
   ```bash
   python -m modules.mcp_server
   ```

3. Check for import errors in `modules/mcp_server.py`

### Tools Not Appearing in Cursor

1. Restart Cursor after configuration changes
2. Check Cursor's MCP server logs for connection errors
3. Verify the working directory path in configuration

### Database Errors

1. Ensure `scoring_history.db` exists in project root
2. Check file permissions on the database
3. Verify no other process has an exclusive lock

## Development

To add new tools:

1. Add the tool implementation function in `modules/mcp_server.py`
2. Add the Tool definition in `create_mcp_server()` → `list_tools()`
3. Add the handler in `call_tool()`
4. Update this documentation

