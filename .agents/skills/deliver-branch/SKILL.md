---
name: deliver-branch
description: >-
  Use when the user asks to deliver, ship, land, or merge the current branch to master:
  commit, push, open the PR, get CI green (fixing failures), merge, then git fetch and
  fast-forward local master. Also for "merge my PR and update master" or "finish this branch".
---

# Deliver branch (compiled harness)

Ship the **current feature branch** end to end. The deterministic steps are done by
`scripts/agent_skills/deliver_branch.py`. Every step returns JSON, and each can be re-run
safely. Only fixing a red CI check needs your judgment.

Run it from the worktree the branch is checked out in. Delivering is outward-facing, so
use it only when the user asked to deliver or merge.

## Steps

```bash
H=scripts/agent_skills/deliver_branch.py
python $H status                      # branch, dirty files, ahead/behind, PR, issue number from the branch name
# 1. Commit anything outstanding (commit-and-push / commit-conventions), then:
python $H push
python $H pr --title "feat(scope): summary (#N)" --body-file <body.md>   # skipped if a PR is already open
python $H checks --wait 1800          # exit 1 lists failing jobs plus a log tail
# 2. Red? Fix the cause (systematic-debugging), commit, `push`, `checks` again. Repeat.
python $H merge                       # refuses on draft / pending / failing checks; deletes the remote branch
python $H sync-master                 # fetch --prune; fast-forward master wherever it is checked out
```

## Around the harness (backlog contract)

- **Before `pr`:** the PR body follows `.github/pull_request_template.md` and must contain
  `Closes #N`; the harness refuses otherwise. Move the card to **Review**:
  `python scripts/agent_skills/backlog_stage.py set-stage <N> --stage review`.
- **After `merge`:** the issue closes automatically. Remove a finished worktree with
  `git worktree remove <path>` and delete the local branch.

## LLM judgment slots

- The PR title and body, including Summary, How to test, and Risk.
- **Fixing CI:** read `failed[].log_tail`, reproduce locally in the matching environment
  (see `wsl-tf-python-runner`), and fix the root cause. Never skip, xfail, or delete a test
  just to turn CI green without telling the user.
- Whether a failure is pre-existing. Check the same job on `master` before calling it
  unrelated.

## Safety (enforced by the harness)

- No force-push. It refuses to run on `master` itself.
- `merge` needs every check green and a PR that is not a draft. The merge method defaults
  to a merge commit, matching the history (`--method squash|rebase` to override).
- `sync-master` only uses `--ff-only`. If `master` is checked out with uncommitted files,
  git refuses to run rather than touch them. A non-fast-forward is **reported**; never
  resolve it with reset or rebase without asking.
