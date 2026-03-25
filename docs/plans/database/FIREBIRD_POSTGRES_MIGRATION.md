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
- `database.backend` (`firebird|postgres`)
- `database.dual_write_enabled`
- `database.postgres.{host,port,db,user,password,sslmode,pool}`
- Electron config:
- `database.engine` (`firebird|postgres`)
- `database.postgres.*` connection block
- MCP config:
- add `postgres-admin`, phase out `firebird-admin` after rollback window
- Keep existing REST/MCP payload contracts stable during migration.

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

## Current Implementation Status (2026-03-23)

### Phase 0 — Schema baseline ✅
- Migration plan: this document
- Alembic configured: `alembic.ini` + `migrations/env.py` + `migrations/versions/0001_initial_schema.py`
- `modules/db_postgres.py` `init_db()` covers all tables

### Phase 1 — Postgres Foundation ✅
- `docker-compose.postgres.yml` — Postgres + pgvector Docker stack
- `scripts/powershell/Setup-PostgresDocker.ps1` — helper to start the container
- `modules/db_postgres.py` — connection pool + full schema init (15 tables, all indexes, HNSW)
- `scripts/python/migrate_firebird_to_postgres.py` — bulk one-time migration

### Phase 2 — Dual-Write (infrastructure ready; not yet activated)

The dual-write plumbing lives in `modules/db.py`:
- `FirebirdCursorProxy` calls `_enqueue_dual_write()` on every `execute` / `executemany`
- A background worker thread drains the queue into Postgres via `db_postgres.PGConnectionManager`

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
docker compose -f docker-compose.postgres.yml up -d
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

### Phase 3 — Python + MCP Cutover (in progress)

`_get_db_engine()` reads `database.engine` from config (default: `"firebird"`). Setting it to
`"postgres"` routes the following read functions to PostgreSQL:

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
| `get_queued_jobs` | `db.py` (hardcoded Postgres query; uses `STRING_AGG` instead of Firebird `LIST()`) |

**SQL translation additions:**
- `FETCH FIRST n ROWS ONLY` → `LIMIT n` added to `_translate_fb_to_pg()` (step 3c)

**To activate:** set `"engine": "postgres"` in `config.json` under `database`.

### Phase 4 — Electron Alignment (not started)

Requires Phase 3 cutover to be stable. Then migrate `electron/db.ts` from `node-firebird`
to a Postgres client (e.g. `pg` or `postgres`).

---

## Assumptions and Defaults

- The exact file path you gave ([migration-plan.md](https://github.com/synthet/electron-image-scoring/blob/master/docs/technical/migrations/firebird-to-postgresql-pgvector-migration-plan.md)) was not found locally; refinement is based on nearby Electron docs:
- `docs/technical/architecture/DATABASE.md`
- `docs/technical/architecture/OVERVIEW.md`
- Day-1 cutover remains Python + MCP; Electron migration is required before final decommission.
- Deployment default remains local Docker Postgres for initial rollout.
