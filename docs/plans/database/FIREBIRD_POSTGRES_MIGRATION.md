# Refined Cross-Repo Migration Plan: Firebird -> PostgreSQL + pgvector

Date: 2026-03-08  
Status: Draft (Refined)  
Scope: image-scoring + electron-image-scoring coordinated migration

## Summary

- Treat this as a **coordinated platform migration** across both repos (`image-scoring` and `electron-image-scoring`), not a frontend-only or backend-only DB split.
- Keep your selected rollout defaults: **phased dual-write**, **Postgres in local Docker**, **Python app + MCP as day-1 cutover scope**.
- Add explicit **Electron migration gates** before final Firebird retirement, aligned with Electron docs that currently recommend Firebird until coordinated migration is ready.

## Key Implementation Changes

1. **Readiness / Governance (Phase 0)**
- Freeze schema baseline from live Firebird and define versioned SQL migrations (move away from implicit startup DDL as migration mechanism).
- Lock migration invariants: preserve IDs, preserve FK behavior, preserve embedding dimension `1280`, preserve API response shapes.
- Add a migration runbook with rollback window and ownership split by repo.

2. **Postgres Foundation (Phase 1)**
- Stand up PostgreSQL + `pgvector` in Docker.
- Create full schema for active tables used by app + pipeline + phase tracking (`IMAGES`, `FILE_PATHS`, `FOLDERS`, `STACKS`, `CLUSTER_PROGRESS`, `CULLING_*`, `JOBS`, `PIPELINE_PHASES`, `IMAGE_PHASE_STATUS`, `JOB_PHASES`, `STACK_CACHE`, plus optional empty tables `IMAGE_EXIF`, `IMAGE_XMP`).
- Map `images.image_embedding` from Firebird blob to `vector(1280)`; add HNSW cosine index.

3. **Data Migration + Dual-Write (Phase 2)**
- Build resumable Firebird->Postgres backfill (chunked by PK, idempotent upserts, sequence `setval` sync).
- Enable **Python-side dual-write** (Firebird primary write, Postgres secondary write with retry queue and replay).
- Keep Firebird as read source until parity gates pass.

4. **Python + MCP Cutover (Phase 3)**
- Add backend-aware DB adapter in `modules.db` (same public function signatures).
- Switch Python reads to Postgres after parity + performance gates.
- Replace `firebird-admin` MCP with `postgres-admin`; keep old Firebird admin in read-only rollback mode during stabilization.

5. **Electron Alignment Before Final Decommission (Phase 4)**
- Add DB provider abstraction in Electron main-process DB layer (`electron/db.ts`) while preserving IPC contracts.
- Migrate Electron from `node-firebird` to Postgres client only after Python cutover stabilizes.
- Remove Firebird-specific runtime assumptions (port checks, auto-start server path, Firebird-only SQL).
- Final Firebird decommission only after Electron + Python both pass production soak on Postgres.

## Public API / Interface Changes

- `image-scoring` config:
- `database.engine` (`firebird|postgres`)
- `database.filename` (used by Firebird mode)
- optional `database.dual_write` (Firebird primary write + Postgres secondary write)
- `database.postgres.{host,port,dbname,user,password}`
- Electron config:
- `database.engine` (`firebird|postgres`)
- `database.postgres.*` connection block
- MCP config:
- add `postgres-admin`, phase out `firebird-admin` after rollback window
- Keep existing REST/MCP payload contracts stable during migration.

### Migration mode config examples

Use the same key names as `modules/config.py` validation and `modules/db_postgres.py` connection loading.

```json
{
  "database": {
    "engine": "firebird",
    "filename": "scoring_history.fdb",
    "dual_write": true,
    "postgres": {
      "host": "127.0.0.1",
      "port": 5432,
      "dbname": "musiq",
      "user": "musiq",
      "password": "musiq"
    }
  }
}
```

- **Firebird only**: set `database.engine` to `firebird`; `database.filename` is required.
- **Postgres only**: set `database.engine` to `postgres`; `database.postgres.host|port|dbname|user` are required.
- **Migration/dual-write mode**: keep `engine=firebird` and set `database.dual_write=true` so Firebird remains the primary store while writes are mirrored to Postgres.

## Test Plan

1. **Data parity**
- Table counts and PK coverage parity per migrated table.
- FK integrity checks in Postgres.
- Sampled row-hash parity on high-value columns.

2. **Embedding/vector correctness**
- Non-null vector count parity.
- Dimension enforcement (`1280`) and conversion validation from Firebird blob.
- Similar search top-K overlap and score tolerance checks.

3. **Behavioral parity**
- Endpoint parity for `/similar`, duplicates, outliers, job/status flows.
- MCP tool parity between old and new admin paths.

4. **Performance + reliability**
- p95 latency targets for similarity and duplicate candidate queries.
- Dual-write retry queue drain tests and failure injection.
- Full rollback drill (toggle reads back to Firebird).

5. **Cross-repo acceptance**
- Python app + MCP pass on Postgres.
- Electron IPC workflows pass after provider switch.
- Only then allow Firebird retirement.

## Current Implementation Status (2026-03-26)

### Phase 0 — Schema baseline ✅
- Migration plan: this document
- Alembic configured: `alembic.ini` + `migrations/env.py` + `migrations/versions/0001_initial_schema.py`
- `modules/db_postgres.py` `init_db()` covers all 17 tables

### Phase 1 — Postgres Foundation ✅
- `docker-compose.yml` — Postgres + pgvector Docker stack (`pgvector/pgvector:pg17`)
- `modules/db_postgres.py` — connection pool (ThreadedConnectionPool 1–20) + full schema init (17 tables, all indexes, HNSW cosine on `image_embedding`)
- `scripts/python/migrate_firebird_to_postgres.py` — chunked, resumable bulk migration with `--dry-run` and `--batch-size` flags
- `scripts/powershell/Setup-PostgresDocker.ps1` — helper to start the container

### Phase 2 — Dual-Write ⚠️ (infrastructure complete; not yet activated)

The dual-write plumbing lives in `modules/db.py`:
- `FirebirdCursorProxy` calls `_enqueue_dual_write()` on every `execute` / `executemany`
- A background worker thread (`_dual_write_worker`) drains the queue into Postgres via `db_postgres.PGConnectionManager`
- `init_dual_write()` starts the worker when `engine="firebird"` AND `dual_write=true`
- `get_dual_write_stats()` returns `{queued, success, fail, queue_depth, enabled}` for monitoring

> **Known limitation:** worker failures are logged and discarded — no retry queue, no dead-letter. Silent data divergence is possible under Postgres errors.

**To activate dual-write** (set `dual_write: true` in `config.json` and start Postgres Docker):

```json
"database": {
    "engine": "firebird",
    "filename": "scoring_history.FDB",
    "user": "sysdba",
    "password": "masterkey",
    "dual_write": true,
    "postgres": {
        "host": "127.0.0.1",
        "port": 5432,
        "dbname": "image_scoring",
        "user": "postgres",
        "password": "postgres"
    }
}
```

Start Postgres:

```powershell
docker compose -f docker-compose.yml up -d
```

Init the Postgres schema (one-time):

```bash
# In WSL with ~/.venvs/tf activated:
python -c "from modules.db_postgres import init_db; init_db()"
# Or via Alembic (creates tables + marks revision as current):
alembic upgrade head
```

Bulk-migrate existing Firebird data:

```bash
python scripts/python/migrate_firebird_to_postgres.py
```

Verify parity:

```bash
python scripts/python/migrate_firebird_to_postgres.py --dry-run
```

### Phase 3 — Python + MCP Cutover 🟡 (~85% complete; 2 critical bugs block activation)

#### Transport-layer abstraction (`modules/db_connector/`) ✅

A new connector layer was added to decouple SQL execution from engine selection.
See [`docs/architecture/DB_CONNECTOR.md`](../../architecture/DB_CONNECTOR.md) for full design.

| `database.engine` | Connector | Notes |
|---|---|---|
| `"firebird"` (default) | `FirebirdConnector` | wraps `db.get_db()`; dual-write passthrough |
| `"postgres"` | `PostgresConnector` | wraps psycopg2 pool; auto-translates via `_translate_fb_to_pg()` |
| `"api"` | `ApiConnector` | HTTP proxy to `/api/db/query`; for remote workers |

Five functions were migrated to the connector as proof-of-concept: `get_image_by_hash`,
`get_image_details`, `update_image_field`, `create_job`, `enqueue_job`.
Full migration of remaining functions in `db.py` is a follow-on task.

#### Read/write routing via `_get_db_engine()` (~60 functions)

Setting `"engine": "postgres"` in `config.json` routes the following to PostgreSQL:

| Function | Module |
|---|---|
| `find_image_id_by_path` | `db.py` |
| `find_image_id_by_uuid` | `db.py` |
| `get_all_folders` | `db.py` |
| `get_job` | `db.py` |
| `get_image_phase_statuses` | `db.py` |
| `get_all_phases` | `db.py` |
| `get_embeddings_for_search` | `db.py` |
| `get_embeddings_with_metadata` | `db.py` |
| `get_image_count` | `db.py` |
| `get_images_paginated_with_count` | `db.py` |
| `get_all_paths` | `db.py` |
| `get_resolved_path` | `db.py` |
| `get_image_details` | `db.py` |
| `get_image_by_hash` | `db.py` |
| `get_job_phases` | `db.py` |
| `get_jobs` | `db.py` |
| `get_all_images` | `db.py` |
| `get_incomplete_records` | `db.py` |
| `get_queued_jobs` | `db.py` (uses `STRING_AGG` instead of Firebird `LIST()`) |
| `get_folder_by_id` | `db.py` |
| `get_image_exif` | `db.py` |
| `get_image_xmp` | `db.py` |
| `get_culling_session` | `db.py` |
| `get_active_culling_sessions` | `db.py` |
| `get_session_picks` | `db.py` |
| `get_session_groups` | `db.py` |
| `get_images_in_stack` | `db.py` |
| `get_stack_count` | `db.py` |
| `get_clustered_folders` | `db.py` |
| `get_phase_id` | `db.py` |
| `get_images_by_folder` | `db.py` |
| `get_nef_paths_for_research` | `db.py` |
| `get_image_ids_by_paths` | `db.py` |

#### SQL translation (`_translate_fb_to_pg()`)

Rules implemented in `modules/db.py` (line ~231):
- `UPDATE OR INSERT … MATCHING` → `INSERT … ON CONFLICT DO UPDATE`
- `SELECT FIRST n` / `FETCH FIRST n ROWS ONLY` → `LIMIT n`
- `DATEDIFF(UNIT FROM a TO b)` → `EXTRACT(…)` ⚠️ **BUG — see below**
- `?` → `%s` (outside string literals)
- `RAND()` → `RANDOM()`, `LIST(col, sep)` → `STRING_AGG(col, sep)`
- `substr()` → `substring()`, `length()` → `char_length()`

#### PostgreSQL schema additions
- `keywords_dim` and `image_keywords` tables added to `db_postgres.init_db()`
- `execute_write()` and `execute_write_returning()` helpers in `db_postgres.py`

#### ⚠️ Known bugs blocking activation

**BUG 1 — DATEDIFF division operator** (`modules/db.py` ~line 278–280):
```python
# WRONG (backslash instead of forward-slash):
f'(EXTRACT(EPOCH FROM ({end} - {start})) \ 60)::INTEGER'   # MINUTE
f'(EXTRACT(EPOCH FROM ({end} - {start})) \ 3600)::INTEGER' # HOUR
# Fix: replace \ with /
```
Affects `DATEDIFF(MINUTE …)` and `DATEDIFF(HOUR …)` translations — silently returns wrong values.

**BUG 2 — `FirebirdCursorProxy._translate_query()` is incomplete** (`modules/db.py` ~line 145):
The proxy's internal `_translate_query()` only handles `substr`→`substring` and
`length`→`char_length`. It does **not** call `_translate_fb_to_pg()`, so dual-write
enqueues partially-translated SQL (missing UPSERT, DATEDIFF, FETCH FIRST). The worker
re-translates on dequeue, partially masking the issue, but the pre-enqueue pass is
inconsistent.

**To activate Phase 3:** fix both bugs, then set `"engine": "postgres"` in `config.json`.

### Phase 4 — Electron Alignment ❌ (not started)

Requires Phase 3 cutover to be stable. Then migrate `electron/db.ts` from `node-firebird`
to a Postgres client (e.g. `pg` or `postgres`).

---

## Assumptions and Defaults

- The exact file path you gave ([migration-plan.md](https://github.com/synthet/electron-image-scoring/blob/master/docs/technical/migrations/firebird-to-postgresql-pgvector-migration-plan.md)) was not found locally; refinement is based on nearby Electron docs:
- `docs/technical/architecture/DATABASE.md`
- `docs/technical/architecture/OVERVIEW.md`
- Day-1 cutover remains Python + MCP; Electron migration is required before final decommission.
- Deployment default remains local Docker Postgres for initial rollout.
