---
type: Report
title: Deliver to master — runbook (2026-10-02)
description: Completes partial delivery from Claude session export (PR #470 merged; #471 and local model-selection work remaining). Run scripts/powershell/Consolidate-DeliverToMaster.ps1 from a normal terminal (not blocked by Cursor PreToolUse hooks).
resource: reports/deliver-master-runbook-2026-10-02.md
tags: [report, delivery, git]
timestamp: 2026-10-02T00:00:00Z
okf_version: 0.1
status: active
---

# Deliver to master — runbook (2026-10-02)

**Context:** Session log [`2026-10-01-203438-local-command-caveatthe-command-below-was-run-d.txt`](../../2026-10-01-203438-local-command-caveatthe-command-below-was-run-d.txt) records:

- **Done:** PR **#470** merged to `master` (v1 reviews, promotion gate, tests).
- **Pending:** PR **#471** (`feat/scene-route-412`, closes **#412**) — merge after green CI.
- **Local:** `feat/scene-route-412` may be behind `origin`; uncommitted work includes label-free **model selection** (`modules/score_analytics/model_selection.py`, `model_selection_report.py`, wiki reports) and related docs.
- **Config:** `localization.enabled` and `scene_route` (SigLIP2 `wildlife_bird` 0.065) are now **on** in [`config.example.json`](../../config.example.json); copy into your gitignored `config.json` if you want the same at runtime.

**Cursor agent terminal:** If every command fails with `D:\scripts\agent_harness\hook.py`, fix [`.claude/settings.json`](../../.claude/settings.json) (absolute path to `hook.py`) and **reload the window**, or run the script below in **Windows Terminal / PowerShell outside Cursor**.

## One-shot (recommended)

```powershell
cd D:\Projects\image-scoring-backend
.\scripts\powershell\Consolidate-DeliverToMaster.ps1 -Execute
```

Dry-run first (default):

```powershell
.\scripts\powershell\Consolidate-DeliverToMaster.ps1
```

## What the script does

1. `git fetch origin`
2. On `feat/scene-route-412`: stash if needed, `git pull --ff-only origin feat/scene-route-412`
3. **Commit 1** — analytics: model selection module, report script, study modules, tests (excludes `models/*.pt`, `reports/model_selection/`, large snapshot gzip)
4. **Commit 2** — docs: model-selection + deliver wiki pages, `INDEX.md`, `log.md`, feature doc 11
5. **Commit 3** — config example + harness hook paths (if changed)
6. `git push origin feat/scene-route-412`
7. If PR **#471** is open: `gh pr checks 471 --watch` then `gh pr merge 471 --merge --delete-branch`
8. `git checkout master && git pull --ff-only origin master`
9. If model-selection commits landed after #471 merged: open/follow a new PR from a fresh branch (script prints instructions)

## Manual fallback (from session export)

```powershell
gh pr checks 471 --watch
gh pr merge 471 --merge --delete-branch
python scripts/agent_skills/deliver_branch.py sync-master
git worktree remove ../isb-deliver  # if the temp worktree still exists
```

## After merge

- Regenerate label-free report: `docker exec image-scoring-gpu-shell python scripts/analysis/model_selection_report.py --out reports/model_selection/latest`
- Blind study: [model-selection-codex-handoff-2026-10-02.md](model-selection-codex-handoff-2026-10-02.md)
