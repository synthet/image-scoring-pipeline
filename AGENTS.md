# AI Agents Configuration

This document describes the AI agents and MCP (Model Context Protocol) server integration for the Image Scoring project.

## Overview

The Image Scoring project provides an MCP server that enables AI agents (like Cursor IDE's AI assistant) to interact with the application for debugging, monitoring, and analysis tasks.

## MCP Server: `image-scoring`

The MCP server exposes 21 debugging and diagnostic tools that allow AI agents to:

- **Query and analyze** the Firebird database
- **Monitor** scoring and tagging jobs
- **Diagnose** errors and system issues
- **Track** performance metrics
- **Validate** configuration and file paths
- **Access** debug logs

### Configuration

The MCP server is configured in `mcp_config.json`:

```json
{
  "$schema": "https://raw.githubusercontent.com/modelcontextprotocol/servers/main/schema/mcp-config.schema.json",
  "mcpServers": {
    "image-scoring": {
      "command": "python",
      "args": ["-m", "modules.mcp_server"],
      "cwd": "/path/to/image-scoring",  // Replace with your project path
      "env": {
        "PYTHONPATH": "/path/to/image-scoring"  // Replace with your project path
      }
    }
  }
}
```

### Setup for Cursor IDE

1. **Copy configuration** to Cursor's MCP settings:
   - Windows: `%APPDATA%\Cursor\User\globalStorage\cursor.mcp\mcp.json`
   - Or merge `mcp_config.json` contents into your existing MCP configuration

2. **Install MCP SDK** (if not already installed):
   ```bash
   pip install mcp
   ```

3. **Restart Cursor IDE** to load the new MCP server

### Running the MCP Server

#### Standalone Mode

```bash
# Direct Python execution
python -m modules.mcp_server

# Using PowerShell script
.\scripts\powershell\Run-MCPServer.ps1

# Using batch file
scripts\batch\run_mcp_server.bat
```

#### Integrated with WebUI

Set environment variable to enable MCP alongside the WebUI:

```powershell
# Windows PowerShell
$env:ENABLE_MCP_SERVER = "1"
python webui.py

# Linux/WSL
ENABLE_MCP_SERVER=1 python webui.py
```

## Available Tools

The MCP server provides 21 tools organized into categories:

### 🔍 Diagnostic Tools (Start Here)

| Tool | Description | Use When |
|------|-------------|----------|
| `get_error_summary` | Quick overview of all errors | Initial investigation, health checks |
| `check_database_health` | Data integrity validation | Before major operations, after migrations |
| `get_model_status` | GPU/model loading status | Scoring failures, GPU issues |

### 📊 Data Query Tools

| Tool | Description | Use When |
|------|-------------|----------|
| `get_database_stats` | Overall database statistics | Understanding collection state |
| `query_images` | Flexible image queries with filters | Finding specific images, analyzing patterns |
| `get_image_details` | Full image information | Investigating specific image issues |
| `execute_sql` | Read-only SQL queries (SELECT only) | Complex queries not covered by other tools |

### ❌ Error Investigation Tools

| Tool | Description | Use When |
|------|-------------|----------|
| `get_failed_images` | Images with missing/failed scores | Finding images that need reprocessing |
| `get_incomplete_images` | Images missing data | Data quality checks |
| `validate_file_paths` | Check if files exist | Finding moved/deleted files |

### ⚡ Performance & Monitoring

| Tool | Description | Use When |
|------|-------------|----------|
| `get_performance_metrics` | Processing statistics | Performance analysis, bottleneck identification |
| `get_runner_status` | Active job status | Monitoring active processing |
| `get_recent_jobs` | Job history | Reviewing past operations |
| `get_pipeline_stats` | Pipeline state | Understanding current processing state |

### 🔧 Configuration & System

| Tool | Description | Use When |
|------|-------------|----------|
| `validate_config` | Configuration validation | Configuration issues, setup verification |
| `get_config` | Read configuration | Checking current settings |
| `set_config_value` | Update configuration | Adjusting settings (use carefully) |
| `read_debug_log` | Read debug log entries | Investigating runtime issues |

### 📝 Analysis & Utilities

| Tool | Description | Use When |
|------|-------------|----------|
| `get_stacks_summary` | Stack/cluster analysis | Analyzing image clusters |
| `get_folder_tree` | Folder structure with counts | Understanding folder organization |
| `search_images_by_hash` | Find by content hash (SHA256) | Finding duplicates, moved files |

## Common Workflows

### Workflow 1: Investigate Scoring Failures

```
1. get_error_summary → Identify scope of failures
2. get_failed_images → Get specific failed images
3. get_model_status → Check if GPU/models are working
4. get_runner_status → Check if job is still running
5. read_debug_log → See detailed error messages
```

### Workflow 2: System Health Check

```
1. check_database_health → Data integrity
2. get_model_status → System configuration
3. validate_config → Configuration validity
4. get_performance_metrics → Performance baseline
5. validate_file_paths → File system consistency
```

### Workflow 3: Performance Investigation

```
1. get_performance_metrics → Current performance stats
2. get_recent_jobs → Recent job history
3. get_pipeline_stats → Current pipeline state
4. get_runner_status → Active job details
5. execute_sql → Custom performance queries if needed
```

### Workflow 4: Data Quality Audit

```
1. get_database_stats → Overall statistics
2. check_database_health → Integrity issues
3. get_incomplete_images → Missing data
4. validate_file_paths → Missing files
5. get_error_summary → Error patterns
```

## Quick Decision Tree

**"Why did scoring fail?"**
→ `get_error_summary` → `get_failed_images` → `get_model_status` → `read_debug_log`

**"Is the system healthy?"**
→ `check_database_health` → `get_model_status` → `validate_config`

**"How fast is processing?"**
→ `get_performance_metrics` → `get_runner_status` → `get_pipeline_stats`

**"Find images with X property"**
→ `query_images` with filters → `get_image_details` for specifics

**"What's in the database?"**
→ `get_database_stats` → `get_folder_tree` → `get_stacks_summary`

## Important Notes

- **Database Tools**: Most tools require database access. If database is unavailable, they return a clear error message.
- **Non-DB Tools**: `get_model_status`, `validate_config`, `get_pipeline_stats` work without database.
- **Safety**: `execute_sql` only allows SELECT queries. Dangerous operations are blocked.
- **Performance**: Some tools (like `validate_file_paths`) can be slow on large datasets. Use `limit` parameter.
- **Real-time**: `get_runner_status` and `get_pipeline_stats` show current state, others query historical data.

## Tool Availability

All tools are available when:
- MCP server is running (via Cursor IDE or standalone)
- Database is initialized (for DB-requiring tools)
- Runners are set (for `get_runner_status`, `get_pipeline_stats`)

## Documentation References

- **[Agent Coordination](docs/technical/AGENT_COORDINATION.md)** - Integration and coordination guide for AI agents
- **[MCP Tools Reference](.agent/mcp_tools_reference.md)** - Quick reference guide for AI agents
- **[MCP Debugging Tools](docs/technical/MCP_DEBUGGING_TOOLS.md)** - Detailed documentation
- **[DB Schema](docs/technical/DB_SCHEMA.md)** - Firebird database schema reference
- **[AI Edit Spec](.agent/ai_edit_spec.md)** - Guidelines for AI agents editing code

## Example Agent Interactions

### Example 1: Check System Health

```
Agent: "Check if the system is healthy"
→ Uses: check_database_health, get_model_status, validate_config
→ Returns: Health status, any issues found
```

### Example 2: Find Failed Images

```
Agent: "Find all images that failed scoring"
→ Uses: get_error_summary, get_failed_images
→ Returns: List of failed images with error details
```

### Example 3: Performance Analysis

```
Agent: "How fast is the system processing images?"
→ Uses: get_performance_metrics, get_runner_status
→ Returns: Processing speed, success rates, current job progress
```

## Troubleshooting

### MCP Server Not Available

1. Check if MCP SDK is installed: `pip install mcp`
2. Verify configuration in Cursor IDE settings
3. Check if server is running: `python -m modules.mcp_server`
4. Review logs for connection errors

### Database Tools Return Errors

1. Verify database is initialized: Check `get_model_status` (non-DB tool)
2. Check database connection settings in config
3. Ensure Firebird database is accessible

### Tools Not Appearing in Cursor

1. Restart Cursor IDE after configuration changes
2. Verify `mcp_config.json` syntax is valid JSON
3. Check Cursor IDE console for MCP server errors
4. Ensure Python environment has MCP SDK installed

## Future Enhancements

Potential additions to the MCP server:
- Image scoring tools (trigger scoring jobs)
- Batch operations (bulk updates, exports)
- Advanced analytics (trends, correlations)
- Configuration templates and presets
