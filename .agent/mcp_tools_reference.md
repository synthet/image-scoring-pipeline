# MCP Tools Quick Reference for AI Agents

This document tracks the tools registered in [`modules/mcp_server.py`](../modules/mcp_server.py) (28 tools).

## Connection modes

- **`imgscore-py-stdio`**: **Python workspace** — stdio; `cwd` / `PYTHONPATH` = `${workspaceFolder}` (this repo).
- **`imgscore-el-stdio`**: **Electron workspace** — stdio; `cwd` / `PYTHONPATH` = path to sibling **image-scoring** checkout.
- **`imgscore-py-sse`** / **`imgscore-el-sse`**: SSE to WebUI (same URL; pick the key for your workspace). Default `http://127.0.0.1:7860/mcp/sse` (confirm with `GET /mcp-status` → `expected_sse_url`).
- **`execute_code`**: requires SSE **and** `ENABLE_MCP_EXECUTE_CODE=1` on the WebUI process.

## Tool index

### Diagnostic (4)

1. **`get_error_summary`** — Failed jobs, missing scores, orphans  
2. **`check_database_health`** — Integrity issues (orphans, duplicates, …)  
3. **`get_model_status`** — GPU / CUDA / model load  
4. **`diagnose_phase_consistency`** — `image_id` (+ optional `folder_path`): folder vs image phase mismatch  

### Data query (5)

5. **`get_database_stats`** — Aggregate stats  
6. **`query_images`** — Filters, sort, pagination  
7. **`get_image_details`** — By `file_path`  
8. **`search_images_by_hash`** — By `image_hash`  
9. **`execute_sql`** — `SELECT` only  

### Errors & paths (3)

10. **`get_failed_images`** — Missing key scores (`limit` default 50)  
11. **`get_incomplete_images`** — Broader incomplete rows (`limit` default 100)  
12. **`validate_file_paths`** — Filesystem check (`limit` default 100)  

### Performance & jobs (5)

13. **`get_performance_metrics`** — Recent job stats (`days` default 7)  
14. **`get_runner_status`** — Runner progress/logs  
15. **`get_recent_jobs`** — History (`limit` default 10)  
16. **`get_pipeline_stats`** — Runners + dispatcher + queue sizes  
17. **`run_processing_job`** — `job_type`: scoring | tagging | clustering; `input_path`; optional `args`  

### Config & logs (4)

18. **`validate_config`** — Structural checks (`ok`, `issues`, `warnings`); adds `database_reachable` when DB init succeeded  
19. **`get_config`** — Full config dict  
20. **`set_config_value`** — Dot-key update  
21. **`read_debug_log`** — `lines` default 100  

### Folders, stacks, similarity (6)

22. **`get_folder_tree`** — Optional `root_path`  
23. **`get_stacks_summary`** — Optional `folder_path`  
24. **`search_similar_images`** — `example_path` or `example_image_id`  
25. **`find_near_duplicates`** — Optional `threshold`, `folder_path`, `limit`  
26. **`propagate_tags`** — Keyword propagation (`dry_run` default true)  
27. **`find_outliers`** — Embedding outlier analysis  

### Execute code (1)

28. **`execute_code`** — Python in WebUI; SSE + `ENABLE_MCP_EXECUTE_CODE=1`; assign `result` to return  

## Common workflows

### Scoring failures
```
get_error_summary → get_failed_images → get_model_status → read_debug_log
```

### System health
```
check_database_health → get_model_status → validate_config → validate_file_paths
```

### Performance
```
get_performance_metrics → get_recent_jobs → get_pipeline_stats → get_runner_status
```

### Data quality
```
get_database_stats → check_database_health → get_incomplete_images → validate_file_paths
```

## Important notes

- Most tools need a working DB (`prepare_mcp_embedded` / `db.init_db`).  
- **`get_model_status`** does not require DB.  
- **`validate_config`** structural checks work without DB; MCP adds DB reachability when available.  
- **`execute_sql`**: SELECT only; dangerous patterns blocked.  
- **`validate_file_paths`** / **`get_incomplete_images`** can be heavy — use `limit`.  

## Quick decision tree

- **"Why did scoring fail?"** → `get_error_summary` → `get_failed_images` → `get_model_status` → `read_debug_log`  
- **"Is the system healthy?"** → `check_database_health` → `get_model_status` → `validate_config`  
- **"How fast is processing?"** → `get_performance_metrics` → `get_runner_status` → `get_pipeline_stats`  
- **"Find images with X"** → `query_images` → `get_image_details`  
- **"What's in the database?"** → `get_database_stats` → `get_folder_tree` → `get_stacks_summary`  
