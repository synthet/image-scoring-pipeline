---
name: imgscore-mcp-debug
description: Routine read-only debugging for the image-scoring Python backend via MCP—vexlum search/resolve/execute, scoring/tagging failures, job errors, Postgres questions, DB integrity, and config sanity.
---

# imgscore-mcp-debug

Read-only triage for **image-scoring-pipeline** using MCP. **Do not** mutate DB/config unless the user explicitly asks.

## Preferred entry

**`vexlum`**: **`search(query)`** → **`resolve(action_id)`** → **`execute(action_id, arguments)`**. Contract: [VEXLUM_MCP.md](../../../docs/technical/VEXLUM_MCP.md). When `search` returns several plausible actions, ask **`jev-rw-systemone`** to pick one before `execute`. Protocol: [jev-mcp](../jev-mcp/SKILL.md). Read-tier actions need no confirmation; leave `confirmed` unset during triage.

## Server keys

| Key | Use |
|-----|-----|
| **`vexlum`** | **Default** — `search`, `resolve`, `execute` (tools, `api.*`, `db.*`, `browser.*`) |
| `is-be-mcp`, `is-be-live` | Deprecated; both serve the vexlum tools |

Gallery sibling: **`is-ui-local`** `gallery_status`, **`is-ui-api`** `api_*`.

## Start here

1. **`execute("system.status", {})`** — DB, WebUI API and SSE reachability
2. **`search`**("scoring errors") → **`execute("diagnostics.get_error_summary", {})`**
3. **`execute("diagnostics.check_database_health", {})`**, **`execute("diagnostics.validate_config", {})`**
4. **`execute("jobs.get_failed_images", {"limit": 20})`**, **`execute("jobs.get_run_diagnostics", {"run_id": N})`** when run id known
5. **`execute("logs.search_logs", {"pattern": "error|failed"})`**, **`execute("logs.read_debug_log", {"lines": 100})`**
6. Ad hoc SQL: **`execute("db.schema", …)`** then **`execute("db.query", {"query": "SELECT …"})`** (read-only)

## High-risk (avoid unless asked)

Write and destructive tiers: `maintenance.execute_code`, `maintenance.run_processing_job`, `maintenance.set_config_value`, `maintenance.prune_missing_files`, `db.execute`, `DELETE` / `POST` `api.*`, … `resolve` shows the tier; destructive ones also need `VEXLUM_ALLOW_ELEVATED=1` and a dry-run token.

## HTTP fallback when MCP is down

When **`vexlum`** fails to load, probe the WebUI REST API directly. While it works, the same endpoints are `api.*` actions (`search("…", source="api")`); otherwise call them (prefer `curl.exe` + file bodies on Windows — see [`agent-data-config`](../agent-data-config/SKILL.md)).

**Confirmed read endpoints:**

| Method | Path | Use |
|--------|------|-----|
| GET | `/api/health` | Liveness (`200`) — **not** `/api/status/health` (404) |
| GET | `/api/runs/drive/status` | Auto-drive enabled / last tick / outstanding |
| GET | `/api/jobs/queue` | `queue_size`, `active_runner` |
| GET | `/api/jobs/recent?limit=N` | Recent job status |
| GET | `/api/runs/folder-buckets?limit=N&offset=0` | Planner buckets / phase progress |

**Writes (need user intent):** `POST /api/runs/drive/start`, `POST /api/runs/drive/stop`.

**Do not guess these paths:**

- `/api/status/health` → 404
- `/api/runs/drive/diagnostics` → matches `/api/runs/{run_id}/diagnostics` and fails `int_parsing` on `run_id`

**Queue-cleared condition** (for "process the queue until done"):

1. `folder-buckets` `total == 0` with no `awaiting_*` or `in_flight` buckets
2. `jobs/queue` `queue_size == 0` and `active_runner == null`

Completed scoring / culling / keywords jobs alone are **not** enough — folders can remain at `awaiting_bird_species` afterward. Full-pipeline `target_phases` include `bird_species` (indexing → metadata → scoring → culling → keywords → bird_species).

## Auto-drive & Drive to Complete triage

When investigating auto-drive ticks (e.g. dashboard showing "Last tick: queued 0, skipped N" or badge `in flight cap: N`):

1. **Deferral vs Failure**:
   - `last_tick_reason == 'waiting_in_flight'` and skip reason `in_flight_cap` mean candidate folders are deferred by concurrency throttling (`auto_drive.max_in_flight_jobs`, default 1). These are **not** errors or dropped folders; they will be considered on the next idle tick once the running job finishes.
   - The UI badge `{reason.replace(/_/g, ' ')}: {count}` renders as `in flight cap: N`—this indicates *N folders deferred due to the in-flight cap*, not that the cap is N.
2. **Locating Active Runs**:
   - Check `GET /api/jobs/recent` or `db.count_running_pipeline_jobs()` to identify the in-flight job.
   - Folder bucket sorting assigns `in_flight` items order `99` (below `awaiting_*` buckets). An active folder may not appear at the top of the dashboard table.
   - Distinguish camera subdirectories sharing the same date (e.g. `Z8/.../2026-10-17` vs `Z6ii/.../2026-10-17`).

## References

- [AGENTS.md](../../../AGENTS.md)
- [VEXLUM_MCP.md](../../../docs/technical/VEXLUM_MCP.md)
- [.agent/mcp_tools_reference.md](../../mcp_tools_reference.md)
- [workflows/safe_mcp_diagnostics.md](../../workflows/safe_mcp_diagnostics.md)
