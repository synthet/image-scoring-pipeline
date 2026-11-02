---
name: image-scoring-mcp
description: Vexlum Scoring MCP — backend vexlum (search → resolve → execute over tools, REST, PostgreSQL, browser) and gallery is-ui-mcp / is-ui-live.
---

# Vexlum Scoring MCP server

**Contract:** [docs/technical/VEXLUM_MCP.md](../../../docs/technical/VEXLUM_MCP.md). Old ids and envelopes: [MCP_SEARCH_DISPATCH.md](../../../docs/technical/MCP_SEARCH_DISPATCH.md) (deprecated). Action registry: [`mcp/action_registry.json`](../../../mcp/action_registry.json). Full legacy index: [`.agent/mcp_tools_reference.md`](../../mcp_tools_reference.md). **Safe triage:** [`.agent/workflows/safe_mcp_diagnostics.md`](../../workflows/safe_mcp_diagnostics.md).

## Critical rules (vexlum)

1. **Three tools:** `search`, `resolve`, `execute`. `dispatch` and `sse_status` are deprecated aliases. There is no raw `execute_sql` or `get_error_summary` tool — those are legacy names; pass them to `resolve` to get the `action_id`.
2. **`search` → `resolve` → `execute`** when the action is not already known. `resolve` returns the input schema, tier, `requires` and an example call. `search(..., include_schemas=True)` also returns schemas.
3. **Ids:** `category.name` for Python tools (`diagnostics.get_error_summary`), `api.<tag>.<operationId>` for REST, `db.schema|query|execute`, `browser.*`, `system.status|categories`. `resolve` also accepts legacy tool names, REST `operationId`s and `"METHOD /path"`.
4. **On `unknown_action`**, read `details.suggestions` and `details.hint` — do not guess another id from AGENTS.md.
5. **Tiers:** `read` runs immediately. `write` needs `confirmed=true` (preview first with `dry_run=true`). `destructive` (`db.execute`, `DELETE` API, `maintenance.prune_missing_files`, `maintenance.rebase_file_paths`, `maintenance.execute_code`, `browser.run_code_unsafe`) needs `VEXLUM_ALLOW_ELEVATED=1` on the vexlum process, a `dry_run=true` that returns `data.confirm_token`, then `confirmed=true` with that token and the same arguments. Run writes only when the user asked for them.
6. When `search` returns several plausible `action_id`s, ask Jev to pick one (include a `none` option) before `execute`. Protocol: [jev-mcp](../jev-mcp/SKILL.md). Config rerank (`typesafe.mcp_search_rerank`) is a separate server-side path and stays off unless enabled.

## Setup

Copy [`.cursor/mcp.example.json`](../../../.cursor/mcp.example.json) → `.cursor/mcp.json`. Build `cd mcp-server && npm ci && npm run build`, then attach **`vexlum`** (Node `mcp-server/dist/vexlum.js`; the Python worker runs in `image-scoring-gpu-shell` on Windows). Set `VEXLUM_USE_WSL=1` only when Ubuntu `~/.venvs/tf` should be used instead. `api.*` actions need the WebUI running (`webui_unavailable` otherwise); `db.*` and most tools only need PostgreSQL.

CLI with the same catalog: `scripts\vexlum.cmd search|resolve|exec|list|status` (TS host, includes `browser.*`) or `python -m modules.vexlum …` in gpu-shell.

## Preferred workflow (backend)

```text
search("why did scoring fail")                    # step 1 — required when unsure
resolve("diagnostics.get_error_summary")          # step 2 — schema, tier, example
execute("diagnostics.get_error_summary", {})      # step 3
```

## Common tool actions

The catalog also has every REST operation (`search("…", source="api")`) and `db.*`. Counts: [VEXLUM_MCP.md](../../../docs/technical/VEXLUM_MCP.md#catalog-sources).

| action_id | Tier | Use for |
|-----------|------|---------|
| `system.status` | read | Catalog counts, DB, WebUI API and SSE reachability |
| `diagnostics.run_doctor` | read | `scripts/doctor.py` equivalent (`no_gpu`, `json`) |
| `diagnostics.get_error_summary` | read | Failed jobs, missing scores, stale running |
| `diagnostics.check_database_health` | read | Orphans, duplicates, integrity |
| `diagnostics.validate_config` | read | Config structure + optional DB ping |
| `diagnostics.get_database_engine_info` | read | Engine, connector, ping |
| `diagnostics.verify_environment` | read | Host, Python, deps |
| `diagnostics.get_model_status` | read | GPU / model load |
| `diagnostics.diagnose_phase_consistency` | read | **Requires `image_id`**; optional `folder_path` |
| `diagnostics.get_stale_running_phase_status` | read | IPS rows stuck `running` |
| `logs.read_debug_log` | read | Tail `debug.log` |
| `logs.get_server_log_tail` | read | Tail `webui.log` / `debug.log` |
| `logs.search_logs` | read | Regex grep on log tails |
| `config.get_config` | read | Redacted config |
| `jobs.get_failed_images` | read | Images **missing score columns** (not per-job failures) |
| `jobs.get_image_pipeline_failures` | read | **`job_image_actions` failed** for one image (`image_id` or `file_path`) |
| `jobs.get_run_diagnostics` | read | Post-run audit (`run_id`) |
| `jobs.get_runner_status` | read | In-process runners (WebUI process; often empty from stdio) |
| `jobs.get_recent_jobs` | read | Job history |
| `jobs.get_job_details` | read | One job by `job_id` |
| `data.query_images` | read | Filtered listing (folder, scores, keywords) |
| `data.get_image_details` | read | Full row by `file_path` |
| `data.get_database_stats` / `data.get_folder_tree` / `data.get_stacks_summary` | read | Former full-profile-only tools |
| `db.schema` | read | Postgres `information_schema` (before SQL) |
| `db.query` | read | One `SELECT` / `WITH … SELECT` (`query`, optional `params`, `max_rows`) |
| `db.execute` | destructive | One write/DDL statement; dry run executes and rolls back |
| `data.get_embedding_stats` | read | Embedding coverage |
| `support.export_debug_bundle` | write | Redacted zip |
| `maintenance.run_processing_job` | write | Needs in-process runners (WebUI); from gpu-shell prefer `api.*` job endpoints |
| `browser.navigate` / `browser.snapshot` | read | Playwright — open URL, accessibility snapshot |
| `browser.click` | write | Playwright — click element (`target` from snapshot) |
| `browser.run_code_unsafe` | destructive | Playwright RCE |

### Common mistakes

| Wrong | Right |
|-------|-------|
| `execute("execute_sql", …)` | Works (legacy name resolves), but prefer `db.query` |
| `db.query` with `UPDATE`/`DELETE` | Rejected — `db.execute` (destructive tier) |
| Retrying a destructive call with changed args and the old token | Dry-run again; the token is bound to the exact arguments (10 min TTL) |
| `execute("diagnostics.diagnose_phase_consistency", {"folder_path": "…"})` only | **Must include `image_id`**; use `data.query_images` to find candidates first |
| `jobs.get_failed_images` for one image job trace | `jobs.get_image_pipeline_failures` with `image_id` or `file_path` |
| Raw tool name from AGENTS.md inventory | `resolve("<name>")` → use the returned `action_id` |

## Server keys

| Key | Tools |
|-----|-------|
| **`vexlum`** | **`search`**, **`resolve`**, **`execute`** (stdio; gpu-shell worker) |
| `is-be-mcp`, `is-be-live` | **Deprecated** — both now serve the vexlum tools |
| **`is-ui-mcp`** | Gallery — **`search`**, **`dispatch`** |
| **`is-ui-live`** | Gallery SSE — live IPC when Electron dev is running |

## Workflows

### Debug scoring failure

```text
search("scoring failure")
execute("diagnostics.get_error_summary", {})
execute("jobs.get_failed_images", {"limit": 20})
execute("logs.search_logs", {"pattern": "error|failed"})
```

### Per-image pipeline failure

```text
search("pipeline failures for image")
execute("jobs.get_image_pipeline_failures", {"file_path": "/mnt/d/Photos/…/DSC_0001.NEF"})
execute("data.get_image_details", {"file_path": "/mnt/d/Photos/…/DSC_0001.NEF"})
```

### Custom SQL

```text
execute("db.schema", {"table_name_prefix": "image"})
execute("db.query", {"query": "SELECT COUNT(*) FROM images WHERE …", "params": []})
```

### REST endpoint

```text
search("start scoring for a folder", source="api")
resolve("api.<tag>.<operationId>")                 # path/query params top-level, JSON body in `body`
execute("api.<tag>.<operationId>", {...}, dry_run=true)
execute("api.<tag>.<operationId>", {...}, confirmed=true)
```

### Export debug bundle

```text
execute("support.export_debug_bundle", {}, confirmed=true)
```

### Browser automation (Playwright via vexlum)

No separate **`playwright`** MCP server — use **`browser.*`** actions:

```text
search("browser navigate webui")
execute("browser.navigate", {"url": "http://127.0.0.1:7860/ui/"})
execute("browser.snapshot", {})
```

Disable with `MCP_PLAYWRIGHT_ENABLED=0`. Regenerate registry: `node scripts/generate_playwright_registry.mjs`.

### Gallery + backend

1. **`is-ui-mcp`** → `search("gallery status")` → `dispatch("local.gallery_status", {})`
2. **`is-ui-mcp`** → `dispatch("api.api_health", {})` when backend WebUI is up
3. Pipeline/DB triage on **`vexlum`**

## execute_code

`maintenance.execute_code` (destructive) works only inside the WebUI process (`/mcp/sse`) with **`ENABLE_MCP_EXECUTE_CODE=1`**. Assign to `result` to return a value.
