# Image Scoring Project - LLM Context Guide

## Project Overview

Automated image scoring system using:

- **MUSIQ** (TensorFlow) models: KonIQ, SPAQ, PaQ-2-PiQ, AVA
- **LIQE** (PyTorch/CLIP-based) via wrapper/subprocess

Primary goals:

- Score technical + aesthetic quality for images (RAW/JPG)
- Store results in the database (and/or per-image JSON)
- Support workflows like **Stacks** (clustering) and **Culling**

## Current Architecture (high level)

- **Language**: Python (Windows-first, with optional WSL/GPU workflows)
- **UI**: Gradio-based Web UI (`webui.py` + `modules/ui/`)
- **Database**: Firebird `.FDB` (e.g. `SCORING_HISTORY.FDB`) accessed via `modules/db.py`
- **Pipeline**: orchestration code in `modules/pipeline.py` / `modules/engine.py`

## Entry points

Common ways to run the project:

- **Run scoring (Windows / PowerShell)**: `Run-Scoring.ps1`
- **Run scoring (Windows / batch wrapper)**: `run_scoring.bat`
- **Run the Web UI**: `python webui.py` (or `run_webui.bat` / `run_webui_docker.bat`)

Legacy/original helper scripts (still present but not the primary docs path):

- `scripts/powershell/process_nef_folder.ps1`

## Key code locations

| Area | Path |
|------|------|
| UI | `modules/ui/` |
| DB | `modules/db.py` |
| Scoring logic | `modules/scoring.py`, `modules/engine.py` |
| Standalone MUSIQ runner | `scripts/python/run_all_musiq_models.py` (`MultiModelMUSIQ`) |
| LIQE integration | `modules/liqe_wrapper.py`, `scripts/python/score_liqe.py` |
| MCP server | `modules/mcp_server.py` |

## Scoring weights

See **[current_model_weights.md](../reference/models/current_model_weights.md)**.

## Critical rules / invariants

1. **Graceful degradation**: if LIQE (or any optional model) fails, the system must still complete scoring with remaining models.
2. **Paths**: prefer normalized absolute paths; be careful with Windows vs WSL path conversions.
3. **DB integrity**: avoid breaking schema assumptions in `modules/db.py` and existing `.sql` migrations.
4. **Docs consistency**: if you change model weights, model sources, or entry points, update docs under `docs/` accordingly.

## MCP Debugging Tools (For AI Agents)

This project includes an MCP server exposing debugging tools to Cursor and agents. When debugging runtime issues, prefer MCP tools over manual DB/log inspection.

### Quick Reference

**Database & Stats:**
- `get_database_stats`, `query_images`, `get_image_details`, `execute_sql`

**Error & Health Diagnostics:**
- `get_failed_images`, `get_error_summary`, `check_database_health`, `validate_file_paths`

**Performance & Monitoring:**
- `get_performance_metrics`, `get_runner_status`, `get_recent_jobs`, `get_pipeline_stats`

**System Diagnostics:**
- `get_model_status`, `validate_config`, `read_debug_log`

**Analysis Tools:**
- `get_incomplete_images`, `get_stacks_summary`, `get_folder_tree`, `search_images_by_hash`
