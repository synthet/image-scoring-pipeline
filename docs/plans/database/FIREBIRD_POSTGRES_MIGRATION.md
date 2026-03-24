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

## Assumptions and Defaults

- The exact file path you gave ([migration-plan.md](https://github.com/synthet/electron-image-scoring/blob/master/docs/technical/migrations/firebird-to-postgresql-pgvector-migration-plan.md)) was not found locally; refinement is based on nearby Electron docs:
- `docs/technical/architecture/DATABASE.md`
- `docs/technical/architecture/OVERVIEW.md`
- Day-1 cutover remains Python + MCP; Electron migration is required before final decommission.
- Deployment default remains local Docker Postgres for initial rollout.
