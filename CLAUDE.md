# Image Scoring — Python Backend

AI-powered image scoring, tagging, and clustering engine using MUSIQ, LIQE, BLIP, and CLIP models. Serves a FastAPI REST API and Gradio web UI.

## Related Projects

| Project | Path | Role |
|---------|------|------|
| **Python Backend** (this) | `https://github.com/synthet/image-scoring` | AI scoring engine, FastAPI server, Firebird DB schema owner |
| **Electron Frontend** | `https://github.com/synthet/electron-image-scoring` | Desktop UI, IPC query layer, React/Vite |

This project is the **schema authority** — all DDL migrations live in `modules/db.py`. The Electron app queries the same Firebird database but does not modify schema.

## Key Files

- `modules/db.py` — Schema authority, all DDL migrations in `_init_db_impl()` (line ~1009)
- `modules/api.py` — FastAPI REST endpoints (scoring, tagging, clustering jobs)
- `modules/engine.py` — Scoring pipeline orchestrator
- `modules/config.py` — Configuration management
- `modules/mcp_server.py` — MCP server for AI agent integration
- `config.json` — Runtime configuration (model paths, thresholds, DB path)

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

## Commands

- `run_webui.bat` or `python webui.py` — Start WebUI with FastAPI + Gradio (port 7860)
- `python -m modules.mcp_server` — Start MCP server
- `python -m pytest` — Run tests

## Documentation

- `docs/technical/DB_SCHEMA_REFACTOR_PLAN.md` — Schema refactor spec
- `docs/technical/DB_SCHEMA_REFACTOR_IMPLEMENTATION.md` — Implementation plan (4 phases)
- `docs/README.md` — Full documentation index