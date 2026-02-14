---
name: image-scoring-mcp
description: Image Scoring MCP server tools — diagnostics, queries, monitoring, and debugging workflows.
---

# Image Scoring MCP Server

The project includes a Model Context Protocol (MCP) server that exposes 21 diagnostic and query tools. These tools let AI agents interact with the scoring database and system without directly reading code.

## Starting the Server

```bash
# Standalone
python -m modules.mcp_server

# With WebUI (set env var)
ENABLE_MCP_SERVER=1 python webui.py
```

The server implementation is in `modules/mcp_server.py`.

## Tool Categories

### 🔍 Diagnostic (Start Here)

| Tool | Description |
|------|-------------|
| `get_error_summary` | Quick overview of all errors — failed jobs, missing scores, orphans |
| `check_database_health` | Data integrity validation — returns "healthy" / "unhealthy" |
| `get_model_status` | GPU availability, model loading, CUDA/PyTorch/TF status |

### 📊 Data Query

| Tool | Description |
|------|-------------|
| `get_database_stats` | Image counts, score distributions, averages |
| `query_images` | Filter by score range, rating, label, keyword, folder |
| `get_image_details` | Full details for a specific `file_path` |
| `execute_sql` | Custom read-only SQL (SELECT only) |

### ❌ Error Investigation

| Tool | Description |
|------|-------------|
| `get_failed_images` | Images with missing/failed scores |
| `get_incomplete_images` | Images missing any data |
| `validate_file_paths` | Check if referenced files still exist on disk |

### ⚡ Performance & Monitoring

| Tool | Description |
|------|-------------|
| `get_performance_metrics` | Images/hour, success rates, job durations |
| `get_runner_status` | Active job progress and logs |
| `get_recent_jobs` | Job history |
| `get_pipeline_stats` | Queue sizes, processor state |

### 🔧 Configuration

| Tool | Description |
|------|-------------|
| `validate_config` | Check paths, queue sizes, required sections |
| `get_config` | Read full `config.json` |
| `set_config_value` | Update a config key (use carefully) |
| `read_debug_log` | Read recent debug log entries |

### 📝 Analysis

| Tool | Description |
|------|-------------|
| `get_stacks_summary` | Stack/cluster analysis |
| `get_folder_tree` | Folder structure with image counts |
| `search_images_by_hash` | Find images by SHA-256 content hash |

## Common Debugging Workflows

### Scoring Failures
```
get_error_summary → get_failed_images → get_model_status → read_debug_log
```

### System Health Check
```
check_database_health → get_model_status → validate_config → validate_file_paths
```

### Performance Investigation
```
get_performance_metrics → get_recent_jobs → get_pipeline_stats → get_runner_status
```

### Data Quality Audit
```
get_database_stats → check_database_health → get_incomplete_images → validate_file_paths
```

## Quick Decision Tree

- **"Why did scoring fail?"** → `get_error_summary` → `get_failed_images` → `get_model_status`
- **"Is the system healthy?"** → `check_database_health` → `validate_config`
- **"How fast is processing?"** → `get_performance_metrics` → `get_runner_status`
- **"Find images with X"** → `query_images` with filters → `get_image_details`
- **"What's in the database?"** → `get_database_stats` → `get_folder_tree`

## Notes

- Most tools require database access; `get_model_status`, `validate_config`, `get_pipeline_stats` do not.
- `execute_sql` only allows SELECT — dangerous operations are blocked.
- `validate_file_paths` can be slow on large datasets — use the `limit` parameter.
- Full reference: `.agent/mcp_tools_reference.md`
