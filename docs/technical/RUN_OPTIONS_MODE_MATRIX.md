---
type: Technical Reference
title: Run options (single mode)
description: Canonical run mode for POST /api/runs/submit, planner narrowing and dispatcher flags.
resource: technical/RUN_OPTIONS_MODE_MATRIX.md
tags: [runs, planner, api]
timestamp: 2026-10-30T08:00:00Z
okf_version: 0.2
---
# Run options (single mode)

**Canonical `run_mode`:** `process_stale_or_missing`  
**UI label:** Process STALE / MISSING only

As of 2026-05, Vexlum Scoring exposes one pipeline run mode. Legacy modes (`process_unprocessed_or_empty`, `process_all_overwrite`, `validate_and_repair`) and request booleans (`skip_done`, `force_rerun`, `fix_incomplete_stages`, `validation_repair_mode`) were removed from `POST /api/runs/submit`. In-flight jobs that still carry legacy `run_mode` strings are normalized at dispatch time via [`normalize_run_mode()`](../../modules/run_modes.py).

## Behavior

| Aspect | Value |
|--------|--------|
| `run_mode` | `process_stale_or_missing` only |
| Planner | [`run_phase_planner.plan_scope()`](../../modules/run_phase_planner.py) at submit + JIT replan at each phase start |
| Work selection | `explain_phase_run_decision` — missing rows, failed/stale status, executor version drift, incomplete data |
| `skip_existing` on enqueue | `false` (planner-scoped `resolved_image_ids`) |
| Post-run audit | Enabled by default for this mode (see `should_run_post_completion_audit`) |
| Work claims | [`image_phase_work_claims`](../../modules/phase_work_claims.py) prevent duplicate image×phase work across concurrent runs |

## API

- **`POST /api/runs/submit`** — `RunSubmitRequest.run_mode` literal `process_stale_or_missing`; optional `plan_dry_run` returns planner output without enqueueing.
  The submit narrows the requested stages to those with planner work and answers `400 nothing_to_queue` when none remain. The planner only sees registered images, so when the plan includes `indexing` and the scope holds image files indexing would discover but no `images` row exists for, the full requested plan is kept and prerequisites are checked as if nothing were satisfied (#712).
- **`POST /api/runs/plan/preview`** — alias for validation-repair preview (planner dry-run).
- **`POST /api/runs/auto-drive`** — no `run_mode` field; always uses canonical mode.
- **`POST /api/maintenance/heal/{phase_code}`** — spawns heal runs with canonical mode internally.

## Dispatcher flags

[`resolve_run_mode_flags("process_stale_or_missing")`](../../modules/run_modes.py):

| Flag | Value |
|------|-------|
| `skip_done` | false |
| `skip_existing` | false |
| `force_rerun` | false |
| `fix_incomplete_stages` | true |
| `overwrite` | false |
| `force_rescan` | false |

## Frontend

- [`ScopeSelector.tsx`](../../frontend/src/components/scope/ScopeSelector.tsx) — static copy; always submits `run_mode: 'process_stale_or_missing'`.
- Runs **Auto Queue** and **Heal** tools no longer expose mode dropdowns.

## Breaking change

Clients sending removed fields receive **422** (`extra="forbid"` on submit). Clients sending legacy `run_mode` values on submit receive **422** unless the value is exactly `process_stale_or_missing`.
