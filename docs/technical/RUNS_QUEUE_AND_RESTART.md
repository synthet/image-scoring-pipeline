---
type: Technical Reference
title: Runs queue and application restart
description: Durable job queue, delegated culling lifecycle, and restart recovery.
resource: technical/RUNS_QUEUE_AND_RESTART.md
tags: [runs, queue, recovery, database]
timestamp: 2026-10-07T19:53:16Z
okf_version: 0.2
---

# Runs queue and application restart

How batch **runs** (rows in the `jobs` table) behave when the WebUI process stops and starts again.

## Where the queue lives

Queued work is stored in PostgreSQL in the **`jobs`** table (`queue_position`, `enqueued_at`, `status`, `queue_payload`, priority, etc.).

- **[`GET /api/queue`](../../modules/api.py)** (see `get_run_queue`) lists queued jobs via [`db.get_queued_jobs`](../../modules/db.py). With the default `include_related=False`, that path returns rows with **`status = 'queued'`** only.
- **[`JobDispatcher`](../../modules/job_dispatcher.py)** polls [`db.dequeue_next_job()`](../../modules/db.py), which atomically picks the next row with `status = 'queued'` and `cancel_requested = 0`, ordered by priority, `queue_position`, `enqueued_at`, and `id`, then sets it to `running`.

## Startup order

In [`webui.py`](../../webui.py), `app_module.create_ui()` runs **before** [`setup_server_endpoints`](../../modules/ui/app.py), which calls [`api.set_runners`](../../modules/api.py) and starts **`_job_dispatcher.start()`**.

Inside `create_ui`, [`_init_webui_engines`](../../modules/ui/app.py) runs `db.init_db()` then [`PipelineOrchestrator.recover_interrupted_jobs`](../../modules/pipeline_orchestrator.py). Recovery therefore runs **while the dispatcher thread is still stopped**, so stale `running` rows are not raced with a live dequeue.

## Status transitions on restart

| Status before restart | After init |
|----------------------|------------|
| **`queued`** | Unchanged. Still eligible for `dequeue_next_job` in sort order. |
| **`paused`** | Unchanged. **Not** dequeued (`dequeue_next_job` only selects `queued`). Resume explicitly if needed. |
| **`running`** executor | Updated by [`db.recover_running_jobs`](../../modules/db.py) to **`interrupted`** (with `runner_state` / `completed_at` set). It is **not** automatically re-queued. |
| **`running`, `runner_state='waiting_child'`** | Reconciled from its child. A queued child leaves the parent waiting; an interrupted executor child interrupts the parent. |
| **`failed`**, **`completed`**, **`cancelled`** | Unchanged. Not part of the dequeue queue. |

Recovery is invoked from [`modules/ui/app.py`](../../modules/ui/app.py); it calls `recover_running_jobs(mark_as="interrupted")` for running executors, excluding waiting parents.

## Delegated culling runs

Revision 0040 adds durable `jobs.parent_job_id` and `job_phases.delegated_job_id`
links. Culling hands all unfinished downstream stages to one child atomically.
The parent remains running with `runner_state='waiting_child'` and contributes
zero to dispatcher executor capacity. Its culling stage is completed; delegated
stages mirror the child's queued/running/terminal states and actual timestamps.
Keywords completed before a bird-species failure stay completed; only unfinished
stages and the aggregate parent fail. Cancellation and interruption propagate
through every ancestor. Startup and idle dispatcher ticks repair missed projections
without enqueueing duplicate children. Repeated handoff reuses the persisted child.

Pause, resume, and cancel on a parent forward to its linked subtree. Stop requests
target only the runner whose dispatch job ID belongs to that child. Manual parent
stage edits and force-start are rejected. Resume queues the leaf, never the waiting
parent. In-place child restart preserves successful stages and reopens failed or
interrupted parents. Runs UI run-level Retry creates a new independent chain; it
does not replace the old child's links or change the old parent outcome.

If the parent's own post-run audit fails after the child completed successfully,
reconciliation and duplicate child callbacks retain that failure. A finished child
cannot resume its parent as an executor; use a fresh run-level Retry. Cancel/resume
requests that lose a race with child completion return 409 rather than a server error.

Historical payload-only parent IDs remain audit metadata. There is no automatic
backfill of old links or statuses. Foreign keys preserve linked records against
deletion. After an enqueue transaction fails, culling's successful result is retained
but the parent visibly fails with a message identifying the unstarted stages.

### Deployment and rollback (0040)

1. Stop auto-drive submissions and drain current executor work before deploying.
   Stop the backend dispatcher so no old process writes during the upgrade.
2. Create and verify a PostgreSQL backup using
   `scripts/powershell/Backup-Postgres.ps1` (or `scripts/run_postgres_backup.sh`).
3. In the configured backend runtime, inspect `python -m alembic current`, then
   apply `python -m alembic upgrade 0040`. Runtime initialization is also additive;
   the Alembic revision records the deployed schema version explicitly.
4. Start the new backend, run one culling → keywords → bird_species plan, and
   verify the waiting parent, linked child, preserved stage outcomes, and restart
   recovery before re-enabling auto-drive. Historical rows should retain NULL links.
5. For rollback, drain or explicitly cancel every unfinished linked chain first.
   Stop the backend, then run `python -m alembic downgrade 0039` before starting
   the older code. Downgrade rejects active, paused, and interrupted parent chains;
   it removes linkage columns but retains jobs and phase outcomes. It is not a
   recovery mechanism for unfinished work.

These steps describe the production procedure; the implementation tests use only
the isolated `image_scoring_test` database.

## Pipeline auto-resume

After recovery, the orchestrator may look up interrupted **pipeline** jobs (`job_type = 'pipeline'`). If config **`pipeline.auto_resume_interrupted`** is true and no orchestrator run is already active, it calls [`start(folder)`](../../modules/pipeline_orchestrator.py) for that folder — a **new** run while the historical interrupted row remains.

## UI and API

- The React **Runs** page ([`frontend/src/pages/RunsPage.tsx`](../../frontend/src/pages/RunsPage.tsx)) treats **`interrupted`** as **history**.
- **[`POST /api/runs/{run_id}/retry`](../../modules/api.py)** enqueues a **new** job from an existing record; [`RunCard`](../../frontend/src/components/runs/RunCard.tsx) exposes Retry for **`failed`** and **`interrupted`**. The React **run detail** route ([`RunDetailPage`](../../frontend/src/pages/RunDetailPage.tsx)) does **not** submit or retry on load—only `GET` calls. After run-level Retry succeeds, the UI navigates to the **new** `jobs.id` returned by the API. A **higher** id can also appear from **orchestrator follow-up** jobs (e.g. next phase queued with `parent_job_id` pointing at the completed parent) when earlier tooling built the phase plan in the wrong order or when multi-phase work continues as a linked job—inspect `jobs.description`, `job_type`, and `parent_job_id`, not only the Runs UI **Retry** path. [`workflow_healing._enqueue_heal_run`](../../modules/workflow_healing.py) sorts phases with [`sort_phase_value_strings`](../../modules/phases.py) so culling heals run **metadata** before **culling** like the main submit path. To re-run a **single** stage **in place**, use **`POST /api/runs/{run_id}/stages/{stage_code}/retry`** (stage panel **Retry**), which keeps the same run id.

## Restart recovery: `jobs` + `job_phases`

[`recover_running_jobs`](../../modules/db.py) runs during WebUI init (see below). It updates **both** the job row and any **in-flight** phase rows for those jobs so the UI does not leave a stage stuck on “running” after a crash.

### Before the fix (conceptual)

If the server died while Run #305 was active:

- `jobs`: `id=305`, `status='running'`
- `job_phases`: e.g. `job_id=305`, `phase_code='culling'`, `state='running'`

After restart, only `jobs` was set to `interrupted`. **`job_phases` could stay `running`** → run-level badge “Interrupted” but workflow still showed a spinner on that stage.

### After the fix

Same crash state; on restart `recover_running_jobs('interrupted')`:

1. Select running executors, excluding `runner_state='waiting_child'` → e.g. `[305]`.
2. Mark those executors interrupted, with `completed_at` and `runner_state` updated.
3. `UPDATE job_phases SET state = ?, completed_at = ? WHERE job_id IN (…) AND state = 'running'`

Only phases that were **`running`** for those job IDs are updated. Completed/pending/failed phases on the same run (and all rows on other jobs) are unchanged.

### What stays untouched

| Example | Result |
|---------|--------|
| Run #300 already `completed` | Not selected; phases stay as-is |
| Run #306 `queued`, phases `queued` | Not selected; dispatcher picks up the job later |
| Run #305 interrupted: earlier phases `completed` | Still `completed`; only the former `running` phase becomes `interrupted` |

### Code path

`webui.py` `main()` → `create_ui()` → `_init_webui_engines()` → `db.init_db()` then `orchestrator.recover_interrupted_jobs()` → **`db.recover_running_jobs('interrupted')`** → optional pipeline auto-resume → later `api.set_runners()` → `_job_dispatcher.start()`.

## Per-image phase status (`image_phase_status`)

After marking executor runs interrupted, `recover_running_jobs` calls
`reconcile_stale_running_phases_for_jobs` with `in_flight_to='not_started'` so their
unfinished per-image rows remain resumable. Their `last_error` records
`stale_running_reconciled:job_interrupted`.

On WebUI init, **`reconcile_stale_running_phases_for_terminal_jobs`** (see [`modules/db.py`](../../modules/db.py)) also fixes **`running`** rows whose **`jobs`** row is already terminal (completed/failed/canceled/interrupted). Count is surfaced under `job_recovery.reconciled_terminal_job_phase_rows` in config loaded from [`modules/ui/app.py`](../../modules/ui/app.py).

When a job reaches a terminal status via **`update_job_status`**, the same reconcile runs for that **`job_id`** so user-stopped batches (e.g. metadata runner `stop` after setting **`running`** on an image) do not leave stale **`running`** rows.

Optional: set **`processing.strict_job_completion_verify`** to **`true`** in `config.json` to fail single-phase jobs at completion time when **`queue_payload.resolved_image_ids`** is set and any listed image is not terminal for that phase (guards “green run” vs incomplete per-image state).

Diagnostics: MCP **`get_stale_running_phase_status`** lists long-**`running`** `image_phase_status` rows; **`check_database_health`** warns when the count > 0 (older than 1 hour).

### Runner exit audit (brief)

| Runner | `update_job_status` on success path | Notes |
|--------|-------------------------------------|--------|
| [`IndexingRunner`](../../modules/indexing_runner.py) | `completed` / `failed` | User **stop** still ends with **`completed`** (same as metadata). |
| [`MetadataRunner`](../../modules/metadata_runner.py) | `completed` / `failed` | Mid-loop **stop** can leave last image **`running`** until job-level reconcile. |
| [`ScoringRunner`](../../modules/scoring.py) | `completed` / `failed` | Multiple entry paths set terminal status. |
| [`TaggingRunner`](../../modules/tagging.py) | `completed` / `failed` | |
| [`SelectionRunner`](../../modules/selection_runner.py) / clustering | `completed` via `_complete_phase_and_advance` | Uses **`set_job_phase_state`** for culling. |
| [`ClusteringRunner`](../../modules/clustering.py) | `completed` / `failed` | |

## Out of scope for this recovery

- FastAPI **`lifespan`** in [`webui.py`](../../webui.py) (event loop / loop monitor only) does **not** modify `jobs`.

## Related code

| Area | File |
|------|------|
| WebUI init + recovery call | [`modules/ui/app.py`](../../modules/ui/app.py) |
| Stale `running` → `interrupted` | [`modules/db.py`](../../modules/db.py) — `recover_running_jobs` (updates matching `job_phases` rows), `dequeue_next_job`, `get_queued_jobs`, `enqueue_job`; `set_job_phase_state` allows `running` → `interrupted` |
| Background dequeue | [`modules/job_dispatcher.py`](../../modules/job_dispatcher.py) |
| Pipeline recovery / auto-resume | [`modules/pipeline_orchestrator.py`](../../modules/pipeline_orchestrator.py) |
| Dispatcher start | [`modules/api.py`](../../modules/api.py) — `set_runners` |
