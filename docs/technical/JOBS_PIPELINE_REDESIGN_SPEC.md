# Jobs Pipeline Redesign Spec (Refined to Current Codebase)

## Status
- **Type**: Design / implementation specification
- **Scope**: Job submission, queueing, phase orchestration, target resolution, phase state policy
- **Baseline**: Current implementation in `modules/api.py`, `modules/pipeline_orchestrator.py`, `modules/engine.py`, `modules/pipeline.py`, and `modules/db.py`

---

## 1) Problem Statement

The current system has strong phase primitives (`pipeline_phases`, `image_phase_status`) and working runners (scoring/tagging/culling), but orchestration is split across independent runner states and in-memory coordination.

This redesign introduces a **single persisted job queue** and a **job plan model** so all jobs execute one-by-one while preserving per-image phase correctness, version-aware reruns, and folder-level aggregate visibility.

---

## 2) Current-State Summary (As-Is)

### What already exists and should be reused
1. **Phase catalog and statuses** are already modeled (`pipeline_phases`, `image_phase_status`) with statuses `not_started/running/done/skipped/failed`.
2. **Per-image phase updates** are supported by `set_image_phase_status(...)` including attempt count and executor/app versions.
3. **Folder phase summary** is computed from image-level statuses via `get_folder_phase_summary(...)`.
4. **Pipeline orchestrator** exists, but is in-memory and folder-only.
5. **API job creation** exists (`create_job`) and runners can be started/stopped and monitored.

### Current limitations (high-level)
- No persisted global queue of pending jobs.
- No unified job payload for mixed selectors (image IDs + paths + folder IDs + paths).
- Pipeline submit endpoint starts first operation only; downstream operations are not persisted as an executable plan.
- Optional/skippable phase semantics are not represented at job-plan level.
- Crash recovery/resume is not robust because orchestration state is not durable.

---

## 3) Target Architecture (To-Be)

### 3.1 Execution model
- All incoming work is normalized to a **Job** with a persisted **JobPlan**.
- Jobs are stored in a **FIFO queue** (default scheduling policy).
- A single **Dispatcher** runs one job at a time.
- Each job executes ordered phases (`indexing`, `metadata`, `scoring`, `culling`, `keywords`, etc.).
- Each phase executes sequentially over the resolved image set.

### 3.2 Job selectors and normalization
A job request can include any combination of:
- `image_ids`
- `image_paths` (absolute)
- `folder_ids`
- `folder_paths` (absolute)
- `recursive` flag for parent folder traversal

Normalization contract:
1. Resolve selectors to canonical DB identities (`resolved_image_ids`, `resolved_folder_ids`).
2. If path inputs map to already indexed objects, use existing IDs.
3. If path inputs are not yet indexed, index/create DB records first, then use IDs.
4. Deduplicate final image set by image ID.

### 3.3 Phase run policy
For each `(image_id, phase)`:
- Re-run phase when status is not successful (`not_started`, `failed`, `skipped`) **or** executor version is stale.
- Skip phase when status is `done` and executor version is current.
- Always record transition to `running` and terminal state (`done/failed/skipped`).

### 3.4 Aggregate semantics
- Image-level phase state remains source-of-truth.
- Folder/ancestor status is derived as aggregate over descendant images.
- If a new image appears in folder subtree, aggregate status must be invalidated/recomputed so stale “done” does not persist.

---

## 4) Data Model Changes

## 4.1 Jobs table extension
Add durable queue/orchestration fields (can be in `jobs` or split tables):
- `queue_state` (`queued`, `running`, `completed`, `failed`, `canceled`, `interrupted`)
- `queue_priority` (default 100)
- `enqueued_at`, `started_at`, `finished_at`
- `cancel_requested` (bool)
- `dispatcher_owner` / `lease_expires_at` (optional; for safe single-dispatcher lock)
- `idempotency_key` (optional but recommended)

## 4.2 Job payload and phase-plan tables
Add:
- `job_targets(job_id, target_type, target_ref, resolved_id, metadata_json)`
- `job_phases(job_id, phase_code, phase_order, optional, state, skip_reason, started_at, finished_at, error)`

Notes:
- Keep existing `jobs.phase_id` for compatibility, but do not rely on it as the full phase plan.
- `job_phases.state` is independent from `image_phase_status`; it summarizes progress for that phase inside a specific job.

## 4.3 Optional aggregate cache (optional)
Either:
- keep live aggregate query only (current behavior), or
- add cache table `folder_phase_aggregate` with invalidation on image insert/update.

---

## 5) API Contract Changes

## 5.1 New enqueue-first API
`POST /api/jobs`
- Accepts unified selectors and desired phase sequence.
- Returns `job_id`, `queue_state=queued`, `queue_position`.

## 5.2 Queue/status APIs
- `GET /api/jobs/queue` → queued/running jobs with order.
- `GET /api/jobs/{job_id}` → full details: targets, phases, counters, errors.
- `GET /api/jobs/{job_id}/progress` → per-phase and overall progress.
- `POST /api/jobs/{job_id}/cancel` → cancel queued or request graceful stop if running.
- `POST /api/jobs/{job_id}/skip-phase/{phase_code}` → allowed only for optional phases not yet terminal.

## 5.3 Backward compatibility
Existing endpoints (`/scoring/start`, `/tagging/start`, `/clustering/start`, `/pipeline/submit`) should be adapted to enqueue jobs using internal translation to the new job payload.

---

## 6) Dispatcher and Runner Integration

1. Implement `JobDispatcher` service:
   - Poll/claim next queued job.
   - Execute job phase-by-phase.
   - Respect `cancel_requested` checkpoints between images and phases.
2. Keep existing runner logic where possible, but add adaptor methods accepting `resolved_image_ids` instead of only `input_path`.
3. Remove assumptions that “runner busy” means hard reject; replace with enqueue behavior.
4. Persist heartbeat and safe-transition logic for restart recovery.

---

## 7) Detailed Gap Analysis (Current -> Target)

| Gap | Current behavior | Risk | Required change |
|---|---|---|---|
| Global job queue | Runner-specific `is_running` gates start | User requests are dropped/rejected instead of queued | Add persisted FIFO queue + dispatcher |
| Durable orchestration | In-memory orchestrator state | State loss on restart/crash | Persist job phases and execution cursor |
| Target model | Primarily `input_path` | Cannot express mixed IDs/paths cleanly | Unified selector schema + resolver |
| Pipeline chaining | Starts first operation only | Manual continuation, inconsistent multi-step runs | Persist full job phase plan |
| Optional phases | `skipped` status exists but no explicit per-job optional plan | Ambiguous semantics | Add `optional` + explicit skip APIs |
| Version staleness policy | Partly implemented, phase-specific | Drift between phases/runners | Central `should_run_phase` policy |
| Folder reset semantics | Partly implicit via live query/flags | Stale “done” for newly added images | Invalidate/recompute aggregates on new image/index event |
| Idempotency | Not systematic | Duplicate jobs on retry | Support idempotency keys |

---

## 8) Implementation Plan (Incremental)

### Phase A — Queue foundation
1. Add schema migrations for queue fields and `job_phases`.
2. Implement enqueue and queue listing APIs.
3. Introduce dispatcher skeleton and single-job lock.

### Phase B — Unified target resolver
1. Add selector request model.
2. Implement resolver (`paths -> IDs`, recursive folder expansion, dedupe).
3. Store resolved targets per job.

### Phase C — Persisted phase plans
1. Write `job_phases` from requested operations.
2. Execute phases sequentially through dispatcher.
3. Update `job_phases.state` and aggregate counters while running.

### Phase D — Version-aware policy and optional phases
1. Centralize run/skip decision function.
2. Add optional phase controls and skip APIs.
3. Ensure skip semantics in progress and completion conditions.

### Phase E — Recovery and hardening
1. Startup reconciliation (`running -> interrupted` or resume).
2. Add idempotency key handling.
3. Add observability metrics and queue diagnostics.

---

## 9) Acceptance Criteria

1. Multiple job submissions are accepted while work is active and appear in queue order.
2. Exactly one job is `running` at any given time.
3. A job can target mixed selector types (IDs + paths + folders, recursive).
4. Path inputs are resolved to DB IDs when already indexed.
5. Phase re-execution occurs automatically for stale executor version or non-success state.
6. Optional phases can be skipped explicitly and do not block completion.
7. Folder/ancestor phase summaries reflect new-image additions (no stale complete state).
8. Restart does not lose queued jobs and does not leave phantom running jobs.

---

## 10) Non-Goals (for this redesign)

- Parallel multi-job execution.
- Distributed multi-worker execution across machines.
- Replacing existing scoring/tagging/culling algorithms.

---

## 11) Open Questions

1. Should queue scheduling remain strict FIFO, or permit priority lanes for small/single-image jobs?
2. Should canceled running jobs mark in-flight image phases as `failed` with cancel reason, or leave unchanged?
3. Should folder aggregate remain live query only, or move to materialized cache with invalidation?
4. How strict should idempotency be (payload hash + TTL vs explicit client key only)?

---

## 12) Suggested Next PR Breakdown

1. **PR-1:** DB migrations + enqueue APIs + queue listing.
2. **PR-2:** Dispatcher + job phase execution state.
3. **PR-3:** Unified selector resolver and backward-compat endpoint translation.
4. **PR-4:** Optional phases + skip controls + version policy centralization.
5. **PR-5:** Recovery/idempotency/observability hardening.
