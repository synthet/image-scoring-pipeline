# Firebird Schema Optimization & Normalization Refactor Plan

## Summary
- Current state review found schema drift and integrity debt between live DB, runtime DDL, and docs:
- Duplicate indexes on `IMAGES(folder_id)` and `IMAGES(stack_id)`, plus duplicate FK/index coverage in `CULLING_PICKS`.
- High stack integrity drift in live data: `11,902` empty stacks, `12,004` stacks with `best_image_id` not in the stack, `57` stacks with missing best image.
- Query-side side effects: read filters call folder creation (`get_or_create_folder`) instead of pure lookup, which can mutate data during reads.
- DDL source-of-truth drift: runtime DDL in `modules/db.py`, stale SQLite-style migration in `sql/add_resolved_paths_table.sql`, and schema docs mismatch in `docs/technical/DB_SCHEMA.md`.
- Chosen direction: Firebird-first, strict backward compatibility, phased rollout, path-unique identity, hard stack invariants.

## Implementation Changes
1. **Phase 0: Baseline + Migration Framework**
- Add versioned migration ledger table (`SCHEMA_MIGRATIONS`) and stop ad-hoc schema mutation in `_init_db_impl` for new changes.
- Define single DDL authority for Firebird (versioned SQL migrations) and mark legacy SQL script as deprecated.
- Add pre/post migration health SQL checks as repeatable scripts (or MCP tool wrappers).

2. **Phase 1: Integrity Repair + Non-Breaking Performance Fixes**
- Data repair migration:
- Recompute `STACKS.best_image_id` from current `IMAGES.stack_id` members.
- Delete stacks with no members.
- Null out `IMAGES.stack_id` values that reference non-existing stacks.
- Remove duplicate FK constraints on `CULLING_PICKS` (keep one FK per relation) and keep only one supporting index per FK path.
- Remove redundant single-column indexes:
- Drop duplicate `IMAGES(folder_id)` indexes; keep one FK-backed path plus add targeted composite indexes.
- Drop duplicate `IMAGES(stack_id)` index copy.
- Drop redundant `JOBS(phase_id)` duplicate if FK index already covers it.
- Add missing high-value indexes for current workload:
- `IMAGES(created_at)`
- `IMAGES(score_general)`
- `IMAGES(rating)`
- `IMAGES(label)`
- `IMAGES(folder_id, score_general)` for gallery folder+score queries
- `CULLING_PICKS(session_id, group_id, created_at)` for ordered session reads
- Add guard constraints where compatible with current data:
- `rating BETWEEN 0 AND 5 OR rating IS NULL`
- enumerated checks for `cull_decision`, `jobs.status`, `image_phase_status.status`, label domain.
- Refactor read paths to use pure lookup (`get_folder_id_by_path`) instead of `get_or_create_folder` in query APIs to prevent write-on-read.

3. **Phase 2: Normalization (Compatibility-Preserving, Dual-Write)**
- Introduce normalized score model:
- `IMAGE_SCORES(image_id, score_code, score_value, model_version, updated_at)`
- Backfill from `IMAGES` score columns.
- Keep existing score columns in `IMAGES` as compatibility surface during transition.
- Split cold/heavy payloads from hot rows:
- `IMAGE_BLOBS(image_id, metadata_json, scores_json, keywords_json, description_text, embedding_blob, updated_at)`
- Keep legacy columns readable; app writes both old/new during transition.
- Add repository-layer writes so API/UI remain backward compatible while new tables are adopted incrementally.
- Do not remove legacy columns in this phase.

4. **Phase 3: Codebase DB Refactor**
- Break `modules/db.py` into migration + repository modules (images, stacks, paths, pipeline, culling).
- Replace repeated query builders with shared filter builder and typed parameter validation.
- Add invariant repair utility callable from admin/MCP:
- `repair_stacks()`, `dedupe_indexes_report()`, `schema_drift_report()`.

## Public Interfaces / Behavioral Changes
- No breaking API contract in this rollout.
- New internal DB contract:
- `get_folder_id_by_path(path)` (read-only lookup) replaces `get_or_create_folder` in query endpoints.
- New maintenance operations exposed via MCP/admin endpoint:
- `repair_stacks`
- `check_schema_drift`
- `check_index_redundancy`
- Existing endpoints keep payload shape; performance and consistency improve under same API.

## Test Plan
- Migration tests on copy of production DB:
- Pre/post row counts by table.
- Pre/post integrity assertions: zero orphan `stack_id`, zero empty stacks, `best_image_id` always member.
- Constraint/index tests:
- Ensure no duplicate FK constraints remain on `CULLING_PICKS`.
- Ensure index set matches migration spec and no accidental drops of required FK indexes.
- Functional regression tests:
- Gallery filters/sorting (rating/label/score/date/folder) unchanged results.
- Culling session queries maintain ordering and result shape.
- Stack create/remove/dissolve workflows preserve invariants.
- Performance checks:
- Compare median latency for representative gallery and culling queries before vs after (target >=20% improvement on hot paths).

## Assumptions
- Firebird remains production DB for this refactor.
- Strict backward compatibility is required for current WebUI/API/Electron consumers.
- Canonical identity remains path-unique (one row per canonical file path).
- Stack consistency is a hard invariant (enforced by migration + ongoing checks).
- Legacy objects remain available during transition; destructive removals are deferred to a later cleanup release.
