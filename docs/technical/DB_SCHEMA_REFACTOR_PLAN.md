# DB Refactor Plan: Hybrid 3NF + Performance Hardening (Firebird, Backward-Compatible)

## Summary
- Target model: **Hybrid 3NF** with **expand-contract** migration and **backward compatibility**.
- Prioritize: integrity constraints + missing indexes first, then normalize high-impact domains (keywords + editable metadata), then query refactor.
- Keep Firebird and existing app contracts stable while introducing normalized structures.

## Current Findings (from live DB + workload)
- Point lookups are under-indexed:
  - `images.file_path` lookup averages ~136 ms.
  - `images.image_uuid` lookup averages ~142 ms.
  - Queries in `electron/db.ts` around lines 745 and 753.
- Keyword discovery is scan-heavy:
  - `SELECT DISTINCT CAST(keywords...) FROM images` averages ~3.5 s.
  - Query in `electron/db.ts` around line 464.
- Referential integrity gaps:
  - `STACKS.BEST_IMAGE_ID` has 57 orphan references.
  - Several relationship columns lack FKs (`IMAGES.JOB_ID`, `IMAGES.STACK_ID`, `IMAGE_PHASE_STATUS.JOB_ID`, `STACK_CACHE.*` refs).
- Redundant constraints/indexes exist:
  - Duplicate FK/index patterns on `CULLING_PICKS` (`FK_*` and `INTEG_13/14` paths).
  - Duplicate single-column indexes on `IMAGES.FOLDER_ID` and `IMAGES.STACK_ID`.
- Normal form issues:
  - `IMAGES.KEYWORDS` as comma-separated text/BLOB violates 1NF for search.
  - Editable metadata duplicated between `IMAGES` and `IMAGE_XMP`; `IMAGE_XMP` currently empty.

## Implementation Changes

### 1) Phase 0: Baseline + Safety
- Take full DB backup and capture a migration snapshot (live ingestion is active, row counts are changing).
- Run pre-migration integrity report: duplicates, orphans, nullability, and lookup latency baselines.

### 2) Phase 1: Integrity + Index Hardening (no contract break)
- Data cleanup:
  - Repair or null invalid `STACKS.BEST_IMAGE_ID` rows.
- Add/strengthen constraints:
  - `UQ_IMAGES_FILE_PATH (FILE_PATH)`.
  - `UQ_IMAGES_IMAGE_UUID (IMAGE_UUID)` (nullable unique allowed).
  - `UQ_FOLDERS_PATH (PATH)`.
  - FKs:
    - `IMAGES.JOB_ID -> JOBS.ID`
    - `IMAGES.STACK_ID -> STACKS.ID`
    - `STACKS.BEST_IMAGE_ID -> IMAGES.ID`
    - `IMAGE_PHASE_STATUS.JOB_ID -> JOBS.ID`
    - `STACK_CACHE.STACK_ID -> STACKS.ID`
    - `STACK_CACHE.REP_IMAGE_ID -> IMAGES.ID`
    - `STACK_CACHE.FOLDER_ID -> FOLDERS.ID`
- Add/reshape indexes for hot paths:
  - `IMAGES(FILE_PATH)` and `IMAGES(IMAGE_UUID)` (via unique constraints).
  - `IMAGES(FOLDER_ID, SCORE_GENERAL DESC)`.
  - `IMAGES(STACK_ID, SCORE_GENERAL DESC)`.
- Remove redundant indexes/constraints only after validation:
  - Keep one canonical index per access path on `IMAGES.FOLDER_ID` and `IMAGES.STACK_ID`.
  - Remove duplicate legacy FK/index artifacts on `CULLING_PICKS`.
- Recompute index statistics after changes.

### 3) Phase 2: Hybrid 3NF Normalization (backward-compatible dual-write)
- Normalize keywords:
  - New `KEYWORDS_DIM(KEYWORD_ID, KEYWORD_NORM UNIQUE, KEYWORD_DISPLAY)`.
  - New `IMAGE_KEYWORDS(IMAGE_ID, KEYWORD_ID, SOURCE, CONFIDENCE, CREATED_AT, PK(IMAGE_ID, KEYWORD_ID))`.
  - Backfill by splitting existing `IMAGES.KEYWORDS`.
  - Add sync triggers/procedures so old `IMAGES.KEYWORDS` remains populated during transition.
- Normalize editable metadata using existing table:
  - Backfill `IMAGE_XMP` from `IMAGES` (rating, label, title, description, keywords, burst fields).
  - Set `IMAGE_XMP` as canonical editable metadata store.
  - Keep mirrored fields in `IMAGES` during compatibility window via dual-write triggers.
- Add CHECK constraints for controlled enums (`label`, `cull_decision`, status domains), with optional later move to dim/FK model.

### 4) Phase 3: Query Refactor in Electron (no IPC break)
- Keep interface shape unchanged, update SQL internals in `electron/db.ts`:
  - Replace keyword filter from `LIKE '%...%'` on blob/text with indexed `EXISTS` on `IMAGE_KEYWORDS`.
  - Replace `getKeywords` scan with direct `KEYWORDS_DIM` read.
  - Refactor folder image counts query to aggregate join instead of correlated subquery.
  - Keep deterministic path join strategy for `file_paths` selection.

### 5) Phase 4: Cutover + Deprecation
- After consistency and performance gates pass, deprecate duplicate metadata columns from `IMAGES` in a major-version migration.
- Keep compatibility views during one full release cycle before drop.

## Public Interfaces / Contracts
- **No breaking IPC/API change** in this cycle.
- New DB objects: `KEYWORDS_DIM`, `IMAGE_KEYWORDS`, new constraints/indexes, compatibility triggers/views.
- Existing read contracts stay intact while storage model improves underneath.

## Test Plan
- Integrity tests:
  - Zero orphan FK rows for all enforced relationships.
  - Unique constraints pass for `FILE_PATH`, `IMAGE_UUID`, `FOLDERS.PATH`.
  - Dual-write consistency checks (`IMAGES.KEYWORDS` vs normalized keyword tables).
- Functional regressions:
  - `getImages`, `getImageDetails`, `getStacks`, `getFolders`, `getKeywords` return contract-equivalent data.
- Performance acceptance (P95 targets):
  - `find by file_path` and `find by image_uuid` under 25 ms.
  - `getKeywords` under 150 ms warm.
  - folder-filtered `getImages` no regression from current baseline.
- Rollback:
  - Backup restore rehearsal and migration down-script validation before production rollout.

## Assumptions
- Decisions locked: **Hybrid 3NF**, **Expand-Contract**, **Backward-Compatible**.
- Firebird remains the engine; additive schema evolution is acceptable.
- Migration runs with controlled ingestion windows when performing backfill and constraint enforcement.
