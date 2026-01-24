# Image Scoring Project - LLM Context Guide

## Project Overview
Automated image scoring system using Google MUSIQ (TensorFlow) and LIQE (PyTorch/CLIP).
**Goal**: Assess technical and aesthetic quality of images (NEF/JPG) and update EXIF tags.

## Core Architecture
- **Language**: Python 3.10+ (Windows Environment)
- **Frameworks**:
  - `TensorFlow 2.x` (MUSIQ models: KonIQ, SPAQ, PaQ2PiQ)
  - `PyTorch` (LIQE model: CLIP-based)
- **Execution**:
  - **Entry Point**: `process_nef_folder.ps1` (PowerShell Orchestrator)
  - **Batch Logic**: `scripts/python/batch_process_images.py`
  - **Scorers**:
    - `run_all_musiq_models.py` (Main Class `MultiModelMUSIQ`)
    - `score_liqe.py` (External CLI wrapper for LIQE)

## Key Locations
| Component | Path | Description |
|-----------|------|-------------|
| **Scripts** | `scripts/` | Python, PowerShell, and Batch scripts. |
| **Docs** | `docs/` | Documentation (Human readable). |
| **Output** | `[ImageFolder]/[ImageName].json` | Per-image scoring data. |
| **Logs** | `scripts/logs/` | Execution logs. |

## Standard Operations

### 1. Run Scoring
```powershell
.\process_nef_folder.ps1 -FolderPath "D:\Photos\..."
```
*Note: This script handles RAW conversion, scoring, and EXIF tagging.*

### 2. Verify Environment
```python
python tests/test_liqe_simple.py
# Check TF
python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

## Critical Rules
1.  **Do not break VILA**: VILA is currently disabled/removed due to TF Hub issues. Do not re-enable without explicit instruction.
2.  **Hybrid Pipeline**: LIQE runs as a subprocess. If it fails, the system **must** continue with MUSIQ scores (graceful degradation).
3.  **Paths**: Always use absolute paths or `os.path.join` for cross-platform safety (though primarily Windows).
4.  **JSON**: JSON output is the source of truth. EXIF is a derivative.

## Scoring Weights (v2.5.2)
-   **KONIQ**: 0.30 (Tech Reliability)
-   **SPAQ**: 0.25 (Tech Discrimination)
-   **PAQ2PIQ**: 0.20 (Artifacts)
-   **LIQE**: 0.15 (Aesthetic/Semantic)
-   **AVA**: 0.10 (Legacy Aesthetic)

## MCP Debugging Tools (For AI Agents)

The project includes an MCP (Model Context Protocol) server that exposes debugging capabilities to Cursor IDE and AI agents. **When debugging issues, prefer using these MCP tools over direct database access or manual inspection.**

### Quick Reference

**Database & Stats:**
- `get_database_stats` - Overall database statistics
- `query_images` - Query images with filters (score, rating, folder, etc.)
- `get_image_details` - Get full details for specific image
- `execute_sql` - Run read-only SQL queries (SELECT only)

**Error & Health Diagnostics:**
- `get_failed_images` - Find images with missing/failed scores
- `get_error_summary` - Summary of all errors and issues
- `check_database_health` - Data integrity checks (orphaned records, duplicates)
- `validate_file_paths` - Check if database paths exist on filesystem

**Performance & Monitoring:**
- `get_performance_metrics` - Processing speed, success rates, throughput
- `get_runner_status` - Current scoring/tagging job status and progress
- `get_recent_jobs` - Recent job history
- `get_pipeline_stats` - Active pipeline state and queue information

**System Diagnostics:**
- `get_model_status` - GPU availability, model loading status, CUDA/PyTorch/TensorFlow info
- `validate_config` - Validate configuration values and paths
- `read_debug_log` - Read recent debug log entries

**Analysis Tools:**
- `get_incomplete_images` - Images missing data
- `get_stacks_summary` - Stack/cluster analysis
- `get_folder_tree` - Folder structure with counts
- `search_images_by_hash` - Find image by content hash

### When to Use MCP Tools

**Instead of:**
- Manually querying the database
- Reading log files directly
- Checking config files manually
- Inspecting runner state in code

**Use MCP tools to:**
- Diagnose why images failed processing
- Check system health before operations
- Monitor job progress
- Validate data integrity
- Investigate performance issues
- Verify GPU/model configuration

**Note:** Some tools (`get_model_status`, `validate_config`, `get_pipeline_stats`) work even when the database is unavailable, making them useful for system-level diagnostics.
