#!/usr/bin/env python3
"""Compiled harness for deliver-branch: current branch -> PR -> green CI -> merged -> local master.

Deterministic steps only. Fixing a red CI check is the one judgment slot and stays with
the agent: ``checks`` reports which jobs failed and the tail of their logs, the agent fixes,
commits and re-runs ``push`` + ``checks``.

Steps (run in order; each is idempotent and safe to repeat):

  status        branch, dirty files, ahead/behind origin, open PR, linked issue
  push          push the current branch (sets upstream on first push)
  pr            open a PR for the branch if none exists (body must carry ``Closes #N``)
  checks        wait for CI on the PR; exit 1 with failing job logs if anything is red
  merge         merge the PR once every check is green (merge commit, delete branch)
  sync-master   git fetch; fast-forward local master wherever it is checked out

Usage (from the branch's worktree):
  python scripts/agent_skills/deliver_branch.py status --json
  python scripts/agent_skills/deliver_branch.py push
  python scripts/agent_skills/deliver_branch.py pr --title "feat(x): y (#N)" --body-file body.md
  python scripts/agent_skills/deliver_branch.py checks --wait 1800
  python scripts/agent_skills/deliver_branch.py merge
  python scripts/agent_skills/deliver_branch.py sync-master

Safety (enforced): never force-pushes, never pushes to or merges from the base branch,
refuses to merge with pending/failing checks, and only ever fast-forwards master
(``--ff-only``); a non-fast-forward is reported, never resolved by reset or rebase.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

BASE = "master"
_ISSUE_RE = re.compile(r"(?:^|[/_-])(\d{2,6})(?:[/_-]|$)")
_CLOSES_RE = re.compile(r"(?i)\b(?:closes|fixes|resolves)\s+#\d+")


class DeliverError(RuntimeError):
    pass


def _run(args: list[str], cwd: Path | None = None, check: bool = True) -> str:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)
    if check and proc.returncode != 0:
        raise DeliverError(f"{' '.join(args)} failed ({proc.returncode}):\n{proc.stderr.strip() or proc.stdout.strip()}")
    return (proc.stdout or "").strip()


def git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    return _run(["git", *args], cwd=cwd, check=check)


def gh(*args: str, check: bool = True) -> str:
    return _run(["gh", *args], check=check)


def current_branch() -> str:
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch in ("HEAD", ""):
        raise DeliverError("detached HEAD: check out the branch to deliver")
    return branch


def _require_feature_branch() -> str:
    branch = current_branch()
    if branch == BASE:
        raise DeliverError(f"on {BASE}: deliver-branch ships a feature branch, not {BASE} itself")
    return branch


def issue_from_branch(branch: str) -> int | None:
    m = _ISSUE_RE.search(branch)
    return int(m.group(1)) if m else None


def open_pr(branch: str) -> dict | None:
    out = gh("pr", "list", "--head", branch, "--state", "open",
             "--json", "number,url,title,body,mergeable,isDraft", "--limit", "1")
    items = json.loads(out or "[]")
    return items[0] if items else None


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def cmd_status(_a) -> dict:
    branch = current_branch()
    dirty = [line for line in git("status", "--porcelain").splitlines() if line.strip()]
    git("fetch", "--quiet", "origin", check=False)
    upstream = git("rev-parse", "--abbrev-ref", "@{u}", check=False)
    ahead = behind = None
    if upstream:
        counts = git("rev-list", "--left-right", "--count", f"{upstream}...HEAD", check=False).split()
        if len(counts) == 2:
            behind, ahead = int(counts[0]), int(counts[1])
    base_behind = int(git("rev-list", "--count", f"HEAD..origin/{BASE}", check=False) or 0)
    pr = open_pr(branch) if branch != BASE else None
    return {
        "branch": branch, "dirty": dirty, "upstream": upstream or None,
        "ahead": ahead, "behind": behind, f"behind_origin_{BASE}": base_behind,
        "issue": issue_from_branch(branch),
        "pr": {k: pr[k] for k in ("number", "url", "title", "mergeable", "isDraft")} if pr else None,
    }


def cmd_push(_a) -> dict:
    branch = _require_feature_branch()
    dirty = [line for line in git("status", "--porcelain").splitlines() if line.strip()]
    if dirty:
        raise DeliverError("uncommitted changes; commit them first (commit-and-push):\n" + "\n".join(dirty[:20]))
    has_upstream = bool(git("rev-parse", "--abbrev-ref", "@{u}", check=False))
    if has_upstream:
        git("push", "origin", branch)
    else:
        git("push", "-u", "origin", branch)
    return {"pushed": branch, "head": git("rev-parse", "--short", "HEAD")}


def cmd_pr(a) -> dict:
    branch = _require_feature_branch()
    existing = open_pr(branch)
    if existing:
        return {"pr": existing["number"], "url": existing["url"], "created": False}
    if not a.title or not a.body_file:
        raise DeliverError("no open PR: pass --title and --body-file to create one")
    body = Path(a.body_file).read_text(encoding="utf-8")
    if not _CLOSES_RE.search(body):
        raise DeliverError("PR body must contain 'Closes #<N>' (backlog contract)")
    url = gh("pr", "create", "--base", BASE, "--head", branch, "--title", a.title, "--body-file", a.body_file)
    return {"url": url.splitlines()[-1], "created": True}


def _checks(pr_number: int) -> list[dict]:
    out = gh("pr", "checks", str(pr_number), "--json", "name,state,bucket,link,workflow", check=False)
    try:
        return json.loads(out or "[]")
    except json.JSONDecodeError:
        return []


def _failed_log_tail(link: str, lines: int = 60) -> str:
    m = re.search(r"/actions/runs/(\d+)/job/(\d+)", link or "")
    if not m:
        return ""
    log = gh("run", "view", m.group(1), "--job", m.group(2), "--log-failed", check=False)
    return "\n".join(log.splitlines()[-lines:])


def cmd_checks(a) -> dict:
    branch = _require_feature_branch()
    pr = open_pr(branch)
    if not pr:
        raise DeliverError("no open PR for this branch (run the 'pr' step)")
    deadline = time.time() + a.wait
    while True:
        checks = _checks(pr["number"])
        pending = [c for c in checks if c.get("bucket") == "pending"]
        failed = [c for c in checks if c.get("bucket") in ("fail", "cancel")]
        if failed or (checks and not pending) or time.time() >= deadline:
            break
        time.sleep(a.poll)
    result = {
        "pr": pr["number"],
        "passed": [c["name"] for c in checks if c.get("bucket") in ("pass", "skipping")],
        "pending": [c["name"] for c in pending],
        "failed": [{"name": c["name"], "workflow": c.get("workflow"), "link": c.get("link"),
                    "log_tail": _failed_log_tail(c.get("link", ""))} for c in failed],
    }
    result["green"] = bool(checks) and not pending and not failed
    return result


def cmd_merge(a) -> dict:
    branch = _require_feature_branch()
    pr = open_pr(branch)
    if not pr:
        raise DeliverError("no open PR for this branch")
    if pr.get("isDraft"):
        raise DeliverError("PR is a draft; mark it ready first")
    state = cmd_checks(argparse.Namespace(wait=0, poll=0))
    if not state["green"]:
        raise DeliverError(f"checks not green: pending={state['pending']} failed={[f['name'] for f in state['failed']]}")
    method = {"merge": "--merge", "squash": "--squash", "rebase": "--rebase"}[a.method]
    # No --delete-branch: gh would try to delete the local branch too, which fails while it
    # is checked out in a worktree. The remote branch is deleted explicitly instead.
    gh("pr", "merge", str(pr["number"]), method)
    git("push", "origin", "--delete", branch, check=False)
    return {"merged": pr["number"], "url": pr["url"], "method": a.method}


def _worktree_holding(branch: str) -> Path | None:
    """Path of the worktree that has ``branch`` checked out, if any."""
    path = None
    for line in git("worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = Path(line.split(" ", 1)[1])
        elif line == f"branch refs/heads/{branch}" and path is not None:
            return path
    return None


def cmd_sync_master(_a) -> dict:
    git("fetch", "--prune", "origin")
    holder = _worktree_holding(BASE)
    before = git("rev-parse", "--short", BASE, check=False)
    if holder is None:
        # Not checked out anywhere: move the ref directly, fast-forward only.
        git("fetch", "origin", f"{BASE}:{BASE}")
        where = "ref only"
    else:
        # Uncommitted changes are fine as long as the fast-forward does not touch them;
        # git refuses (and changes nothing) if it would.
        git("pull", "--ff-only", "origin", BASE, cwd=holder)
        where = str(holder)
    after = git("rev-parse", "--short", BASE)
    return {"master_before": before, "master_after": after, "updated_in": where,
            "matches_origin": after == git("rev-parse", "--short", f"origin/{BASE}")}


STEPS = {
    "status": cmd_status, "push": cmd_push, "pr": cmd_pr,
    "checks": cmd_checks, "merge": cmd_merge, "sync-master": cmd_sync_master,
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Deliver the current branch: PR -> green CI -> merge -> fast-forward master.",
    )
    sub = p.add_subparsers(dest="step", required=True)
    for name in STEPS:
        sp = sub.add_parser(name)
        sp.add_argument("--json", action="store_true")
        if name == "pr":
            sp.add_argument("--title")
            sp.add_argument("--body-file")
        if name == "checks":
            sp.add_argument("--wait", type=int, default=1800, help="seconds to wait for pending checks")
            sp.add_argument("--poll", type=int, default=30)
        if name == "merge":
            sp.add_argument("--method", choices=("merge", "squash", "rebase"), default="merge")
    a = p.parse_args(argv)
    try:
        result = STEPS[a.step](a)
        ok = result.get("green", True) is not False
    except DeliverError as exc:
        result, ok = {"error": str(exc)}, False
    json.dump({"step": a.step, "ok": ok, **result}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
