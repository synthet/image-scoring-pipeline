# Image Scoring — Python Backend

AI-powered image scoring, tagging, and clustering engine using MUSIQ, LIQE, BLIP, and CLIP models. Serves a FastAPI REST API and Gradio web UI.

## Related Projects

| Project | Path | Role |
|---------|------|------|
| **Python Backend** (this) | `https://github.com/synthet/image-scoring` | AI scoring engine, FastAPI server, Firebird DB schema owner |
| **Electron Frontend** | `https://github.com/synthet/electron-image-scoring` | Desktop UI, IPC query layer, React/Vite |

This project is the **schema authority** — all DDL migrations live in `modules/db.py`. The Electron app queries the same Firebird database but does not modify schema.

## Architecture

### Pipeline Phases

Processing is organized into sequential phases defined in `modules/phases.py`:

| Phase | Code | Description |
|-------|------|-------------|
| Indexing | `indexing` | Discover and register image files |
| Metadata | `metadata` | Extract EXIF, XMP, file metadata |
| Scoring | `scoring` | Run ML models (MUSIQ, LIQE, TOPIQ, Q-Align) |
| Culling | `culling` | Cluster similar images |
| Keywords | `keywords` | Generate tags via BLIP/CLIP captioning |

Phase status values: `not_started | running | done | skipped | failed`

### Key Modules

| Module | Role |
|--------|------|
| `modules/db.py` | Schema authority; all DDL migrations in `_init_db_impl()` |
| `modules/api.py` | FastAPI REST endpoints for scoring, tagging, clustering jobs |
| `modules/engine.py` | Batch processor; producer-consumer pipeline orchestrator |
| `modules/pipeline.py` | Low-level pipeline primitives |
| `modules/pipeline_orchestrator.py` | High-level orchestration across phases |
| `modules/phases.py` | Phase definitions (`PhaseCode`, `PhaseStatus` enums) |
| `modules/phases_policy.py` | Rules for when phases can/should run |
| `modules/phase_executors.py` | Per-phase execution logic |
| `modules/job_dispatcher.py` | Routes API job requests to phase executors |
| `modules/config.py` | Config management via `config.json` |
| `modules/scoring.py` | Score computation and normalization |
| `modules/tagging.py` | Keyword/tag generation |
| `modules/clustering.py` | Image clustering (culling) |
| `modules/mcp_server.py` | MCP server for AI agent integration (stdio) |
| `modules/selection.py` | Image selection and filtering |
| `modules/ui/status_gradio.py` | Minimal operator status page served at `/app` |

### ML Models

| Model | Module | Task |
|-------|--------|------|
| MUSIQ | `modules/musiq_wrapper.py` | Multi-scale image quality |
| LIQE | `modules/liqe.py` / `liqe_wrapper.py` | Learned image quality evaluator |
| TOPIQ | `modules/topiq.py` | Top-down image quality |
| Q-Align | `modules/qalign.py` | Quality alignment scoring |
| BLIP/CLIP | `modules/tagging.py` | Captioning and tagging |

### Environment

- **Hybrid:** Windows host + WSL 2 for GPU/ML workloads
- **DB:** Firebird SQL (`SCORING_HISTORY.FDB`), accessed via TCP (port 3050) — never via direct file access between Windows and WSL
- **WebUI:** FastAPI on port 7860; `/ui/` serves the React SPA (primary product UI), `/app` is a minimal Gradio operator status page (threads, profiling, runners, log tail)

## Key Files

- `modules/db.py` — Schema authority, all DDL migrations in `_init_db_impl()`
- `modules/api.py` — FastAPI REST endpoints (scoring, tagging, clustering jobs)
- `modules/engine.py` — Scoring pipeline orchestrator
- `modules/config.py` — Configuration management
- `modules/mcp_server.py` — MCP server for AI agent integration
- `config.json` — Runtime configuration (model paths, thresholds, DB path)
- `webui.py` — Application entry point

## Commands

```bash
# Start WebUI (FastAPI + Gradio, port 7860)
python webui.py
# or on Windows:
run_webui.bat

# Start MCP server (standalone)
python -m modules.mcp_server

# Start MCP server alongside WebUI
ENABLE_MCP_SERVER=1 python webui.py   # Linux/WSL
$env:ENABLE_MCP_SERVER="1"; python webui.py  # PowerShell

# Run tests
python -m pytest
python -m pytest -m "not gpu and not db and not ml"  # fast subset, no hardware deps
python -m pytest tests/test_phases.py -v  # specific file
```

## Testing

Tests live in `tests/`. Markers defined in `pytest.ini`:

| Marker | Meaning |
|--------|---------|
| `gpu` | Requires CUDA GPU |
| `db` | Requires Firebird database connection |
| `ml` | Requires ML dependencies (TF, PyTorch, pyiqa) |
| `wsl` | Must run in WSL/Linux |
| `network` | Requires outbound network |
| `sample_data` | Requires local sample image files |
| `firebird` | Requires Firebird client libraries |

Skip hardware-dependent tests with: `python -m pytest -m "not gpu and not db and not ml and not firebird"`

## Electron Frontend Integration Points

- **Shared DB:** `SCORING_HISTORY.FDB` (Firebird), queried by [db.ts](https://github.com/synthet/electron-image-scoring/blob/master/electron/db.ts)
- **REST API:** Electron calls `http://localhost:7860` for scoring/tagging/clustering jobs (WebUI port)
- **IPC contract:** Electron expects specific column names and result shapes from DB queries — do not rename columns without updating `electron/db.ts`
- **Dual-write:** When modifying keyword or metadata write paths, ensure both `modules/db.py` and `electron/db.ts` stay in sync

## Schema Migration Pattern

All migrations in `_init_db_impl()` follow this pattern:
```python
try:
    cur.execute("ALTER TABLE ...")
    conn.commit()
except Exception:
    conn.rollback()  # idempotent — already applied
```

Helpers: `_table_exists()`, `_column_exists()`, `_index_exists()`, `_constraint_exists()`

## Development Guidelines

- **No hardcoded paths** — use `modules/config.py` and `BASE_DIR`
- **Use `logging` module** — no `print()` in library code
- **Keep public API stable** — REST endpoints, config keys, DB column names
- **Minimal diffs** — prefer targeted edits over rewrites
- **DB column renames** require updating `electron/db.ts` too
- **New score columns** require updating `_init_db_impl()` in `modules/db.py`
- **Secrets** (API keys) go in `secrets.json` (git-ignored), never in `config.json`

## Configuration

`config.json` at repo root. Access via:
```python
from modules.config import get_config_value, get_config_section
val = get_config_value("scoring.force_rescore_default", default=False)
```

## Documentation

- `docs/README.md` — Full documentation index
- `docs/technical/DB_SCHEMA.md` — Firebird schema reference
- `docs/technical/DB_SCHEMA_REFACTOR_PLAN.md` — Schema refactor spec
- `docs/technical/ARCHITECTURE.md` — Architecture overview
- `docs/technical/API_CONTRACT.md` — REST API contract
- `.agent/PROJECT_GUIDE.md` — Agent workflow guide
- `.agent/mcp_tools_reference.md` — MCP tools quick reference
- `AGENTS.md` — MCP server configuration for Cursor/AI agents
