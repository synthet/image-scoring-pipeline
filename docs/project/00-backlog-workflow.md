---
type: Runbook
title: Backlog workflow
description: Operating contract for picking, claiming, and transitioning backlog issues on the synthet Project board, including the stage:* label mirror for cloud sessions.
resource: project/00-backlog-workflow.md
tags: [backlog, project-board, workflow, agents]
timestamp: 2026-09-24T06:00:00Z
okf_version: 0.1
---

# Backlog workflow — claiming work, tracking status, keeping the queue truthful

The canonical task queue is the **GitHub Project board**:

**→ https://github.com/users/synthet/projects/1**

It surfaces issues from both repos:
- `synthet/image-scoring-backend` (this repo) — backend, FastAPI, DB schema
- `synthet/image-scoring-gallery` — Electron / React UI

This document is the **operating contract** every agent (human or AI) must follow
when picking and tracking work. The gallery repo has the same doc — both must stay
in sync.

---

## 1. The board

Two single-select fields drive the workflow:

| Field | Purpose |
|-------|---------|
| **`Stage`** *(primary, custom)* | `Backlog → Ready → Claimed → In Progress → Blocked → Review → Done` — the operator queue every agent reads from and writes to. |
| **`Status`** *(built-in)* | `Todo / In Progress / Done` — required by GitHub PR-close automation; flips to `Done` when a PR with `Closes #N` merges. |

Labels are facets:

| Family | Values |
|--------|--------|
| `area:*` | `python`, `db`, `gradio`, `electron`, `docs` |
| `priority:*` | `p0`, `p1`, `p2`, `p3` |
| `type:*` | `bug`, `feature`, `refactor`, `test`, `chore`, `epic` |
| (special) | `cross-repo` |
| (status) | `obsolete` — superseded or icebox; keep open, Stage = Backlog |

**Epics:** `type:epic` parents with GitHub sub-issues (same repo). Cross-repo epics are paired issues with URLs in the body.

**Obsolete:** Close + `wontfix` when work is dead (e.g. Firebird-only); use `status:obsolete` when superseded but kept for history. See [`backlog-inventory-2026-05.md`](backlog-inventory-2026-05.md).

**Rule:** Edit issues, not files. The repo `TODO.md` is a pointer only.

---

## 2. The agent contract

Every contributor — human or AI — follows the same five steps. Do **all** of them; skipping a step puts the queue out of sync.

### Step 1 — Pick from `Ready`

Open the [Project board](https://github.com/users/synthet/projects/1), filter to **Stage = Ready**, sort by `priority:p0..p3`. Pick the highest-priority unassigned card.

> If `Ready` is empty, ask the maintainer to promote items from `Backlog`. Do not invent new work.

### Step 2 — Claim it

Either run the slash command (Claude Code):

```
/task-claim <issue-number>
```

Or run the equivalent `gh` commands manually:

```bash
# Replace <N> with the issue number, <repo> with image-scoring-backend or image-scoring-gallery
gh issue edit <N> --repo synthet/<repo> --add-assignee @me

# Move the card to Claimed
ITEM_ID=$(gh project item-list 1 --owner synthet --format json \
  --limit 200 \
  | jq -r --argjson n <N> --arg repo "<repo>" \
      '.items[] | select(.content.number==$n and (.content.repository|endswith($repo))) | .id')

gh project item-edit \
  --id "$ITEM_ID" \
  --project-id PVT_kwHOAFXgIs4BWC3c \
  --field-id PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0 \
  --single-select-option-id 1cc70f0b   # Claimed
```

### Step 3 — Flip to `In Progress` on first commit

When you push your first commit on the work branch, move the card to `In Progress`:

```bash
gh project item-edit \
  --id "$ITEM_ID" \
  --project-id PVT_kwHOAFXgIs4BWC3c \
  --field-id PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0 \
  --single-select-option-id 8b22e18e   # In Progress
```

### Step 4 — If blocked, say so

If you hit an external dependency, missing decision, or upstream bug:

1. Move the card to `Stage = Blocked` (option id `4bbe5dd0`).
2. Comment on the issue describing **what** is blocking and **what would unblock it**.

```bash
gh issue comment <N> --repo synthet/<repo> --body "Blocked: <one-line reason + what would unblock>."
```

### Step 5 — Reference the issue in your PR

Your PR description **must** contain a line of the form:

```
Closes #<N>
```

That triggers GitHub's PR-close automation: on merge, the issue closes and the
card moves to `Status = Done`. Move the card to `Stage = Review` while the PR is
open, then to `Stage = Done` after merge (the automation handles `Status` but
the custom `Stage` field is manual).

The PR template enforces an `Issue:` line — see
[`.github/pull_request_template.md`](../../.github/pull_request_template.md).

---

## 3. Cross-repo work

When work touches both repos:

1. File one issue in **each** repo (or use existing pair).
2. Apply the `cross-repo` label to both.
3. In each issue body, link to the counterpart with the full URL.
4. The Project board shows both — group/filter by `cross-repo` to see the pair.

See [`docs/technical/AGENT_COORDINATION.md`](../technical/AGENT_COORDINATION.md)
for cross-repo sync protocol details (API contract changes, schema renames, etc.).

---

## 4. Where things live

| Role | Location |
|------|----------|
| **Canonical queue** | [Project board](https://github.com/users/synthet/projects/1) |
| **Issue trackers** | [backend issues](https://github.com/synthet/image-scoring-backend/issues), [gallery issues](https://github.com/synthet/image-scoring-gallery/issues) |
| **Pointer (this repo)** | [`TODO.md`](../../TODO.md) |
| **Pointer (gallery)** | [gallery `TODO.md`](https://github.com/synthet/image-scoring-gallery/blob/main/TODO.md) |
| **This contract** | here, plus [gallery sibling](https://github.com/synthet/image-scoring-gallery/blob/main/docs/project/00-backlog-workflow.md) |
| **Status narratives** | [`docs/planning/database/NEXT_STEPS.md`](../planning/database/NEXT_STEPS.md), [`docs/features/planned/embeddings/NEXT_STEPS.md`](../features/planned/embeddings/NEXT_STEPS.md) — narrative, not a backlog |

---

## 5. Reference: project + field IDs

For automation/scripts:

| Thing | ID |
|-------|----|
| Project node id | `PVT_kwHOAFXgIs4BWC3c` |
| Project number | `1` |
| Owner | `synthet` (user) |
| `Stage` field id | `PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0` |
| `Backlog` option | `83b7a780` |
| `Ready` option | `ddaf7773` |
| `Claimed` option | `1cc70f0b` |
| `In Progress` option | `8b22e18e` |
| `Blocked` option | `4bbe5dd0` |
| `Review` option | `cb723acb` |
| `Done` option | `73062c96` |

Bootstrap scripts:
- [`scripts/bootstrap_labels.sh`](../../scripts/bootstrap_labels.sh) — re-create the label taxonomy in both repos.
- [`scripts/bootstrap_issues.py`](../../scripts/bootstrap_issues.py) — original migration from legacy `TODO.md`; idempotent (skips by title).

---

## 6. Cloud sessions: `stage:*` labels

Cloud agent sessions (claude.ai/code and similar sandboxes) **cannot reach the Project
board**. Their egress proxy blocks GitHub GraphQL and the `users/*/projectsV2` REST
endpoints, so `gh project …` and `/task-claim` fail there. Instead, the workflow
[`board-stage-sync.yml`](../../.github/workflows/board-stage-sync.yml) mirrors `Stage` onto
issue labels in both repos. It runs every 15 minutes, and immediately on a `stage:*` label
change in this repo.

| Stage | Label |
|-------|-------|
| Backlog | `stage:backlog` |
| Ready | `stage:ready` |
| Claimed | `stage:claimed` |
| In Progress | `stage:in-progress` |
| Blocked | `stage:blocked` |
| Review | `stage:review` |
| Done | `stage:done` |

The contract in §2 is unchanged; a cloud agent follows it through labels:

1. **Pick:** open issues labelled `stage:ready`, sorted by `priority:p0..p3`.
2. **Claim:** assign yourself, then remove `stage:ready` and add `stage:claimed`.
3. **Transition:** swap to `stage:in-progress`, `stage:blocked` (plus the comment from Step 4), or `stage:review`.

Keep **one** `stage:*` label per issue. If labels and board disagree, the newer change
wins: the Stage value's `updatedAt` against the latest `stage:*` `labeled` event. So a
maintainer moving the card on the board overrides an older label, and a label swap
overrides an older board value. Closed board issues always end at Done: the sync sets
their Stage to Done, and any `stage:*` labels they carry collapse to `stage:done`. Closed
issues with no stage label keep their labels. Only issues on the board are synced; PRs
and draft items are skipped. Expect up to 15 minutes of lag for gallery issues.

**Setup (maintainer, once):**
1. Create a classic PAT with `repo` and `project` scopes.
2. Add it to this repo as the Actions secret `BOARD_SYNC_TOKEN`. Without it the workflow skips.
3. Run the workflow manually with `dry_run: true` and review the planned changes. The first run backfills labels on every open board issue.
4. Run it again with `dry_run: false`.

Script: [`scripts/ci/sync_stage_labels.py`](../../scripts/ci/sync_stage_labels.py)
(`--dry-run` to preview). It reuses the IDs and `gh` helpers in
[`scripts/agent_skills/backlog_stage.py`](../../scripts/agent_skills/backlog_stage.py).
