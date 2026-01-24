# MCP Tools Quick Reference for AI Agents

This document provides a quick reference for AI agents using the Image Scoring MCP server debugging tools.

## Tool Categories

### 🔍 Diagnostic Tools (Start Here)
Use these first when investigating issues:

1. **`get_error_summary`** - Quick overview of all errors
   - Shows failed jobs, missing scores, orphaned records
   - No parameters needed
   - **Use when:** Initial investigation, health checks

2. **`check_database_health`** - Data integrity validation
   - Finds orphaned records, duplicates, inconsistencies
   - Returns status: "healthy", "unhealthy", or "error"
   - **Use when:** Before major operations, after migrations

3. **`get_model_status`** - System configuration check
   - GPU availability, model loading, CUDA/PyTorch/TensorFlow status
   - **Use when:** Scoring failures, GPU issues, model loading problems

### 📊 Data Query Tools

4. **`get_database_stats`** - Overall statistics
   - Image counts, score distributions, averages
   - **Use when:** Understanding collection state

5. **`query_images`** - Flexible image queries
   - Filter by: score range, rating, label, keyword, folder
   - Sort and paginate results
   - **Use when:** Finding specific images, analyzing patterns

6. **`get_image_details`** - Full image information
   - Requires: `file_path`
   - **Use when:** Investigating specific image issues

### ❌ Error Investigation Tools

7. **`get_failed_images`** - Images with missing/failed scores
   - Shows which scores are missing
   - Optional: `limit` (default: 50)
   - **Use when:** Finding images that need reprocessing

8. **`get_incomplete_images`** - Images missing data
   - Similar to `get_failed_images` but broader scope
   - **Use when:** Data quality checks

9. **`validate_file_paths`** - Check if files exist
   - Optional: `limit` (default: 100)
   - **Use when:** Finding moved/deleted files

### ⚡ Performance & Monitoring

10. **`get_performance_metrics`** - Processing statistics
    - Images/hour, success rates, job durations
    - **Use when:** Performance analysis, bottleneck identification

11. **`get_runner_status`** - Active job status
    - Progress, logs, running state
    - **Use when:** Monitoring active processing

12. **`get_recent_jobs`** - Job history
    - Optional: `limit` (default: 10)
    - **Use when:** Reviewing past operations

13. **`get_pipeline_stats`** - Pipeline state
    - Queue sizes, processor state, progress
    - **Use when:** Understanding current processing state

### 🔧 Configuration & System

14. **`validate_config`** - Configuration validation
    - Checks paths, queue sizes, required sections
    - **Use when:** Configuration issues, setup verification

15. **`get_config`** - Read configuration
    - Returns full config.json contents
    - **Use when:** Checking current settings

16. **`set_config_value`** - Update configuration
    - Requires: `key`, `value`
    - **Use when:** Adjusting settings (use carefully)

### 📝 Analysis & Utilities

17. **`get_stacks_summary`** - Stack/cluster analysis
    - Optional: `folder_path` filter
    - **Use when:** Analyzing image clusters

18. **`get_folder_tree`** - Folder structure
    - Optional: `root_path` filter
    - **Use when:** Understanding folder organization

19. **`search_images_by_hash`** - Find by content hash
    - Requires: `image_hash` (SHA256)
    - **Use when:** Finding duplicates, moved files

20. **`read_debug_log`** - Read debug logs
    - Optional: `lines` (default: 100)
    - **Use when:** Investigating runtime issues

21. **`execute_sql`** - Custom SQL queries
    - Requires: `query` (SELECT only)
    - Optional: `params` array
    - **Use when:** Complex queries not covered by other tools

## Common Debugging Workflows

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
