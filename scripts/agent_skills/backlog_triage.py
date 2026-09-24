#!/usr/bin/env python3
"""Compiled harness for backlog-triage: snapshot the open queue, then apply a triage plan.

The priority calls are the agent's (see ``.cursor/skills/backlog-triage/SKILL.md``). This
script only gathers facts and carries out an agreed plan.

  snapshot   every open issue with priority, board Stage, age, plus findings
  apply      carry out a plan file (dry run unless --execute)

Board Stage is read from each issue's own ``projectItems`` in the paged GraphQL query, not
from ``gh project item-list``, which can omit recently added items.

Usage (repo root):
  python scripts/agent_skills/backlog_triage.py snapshot [--repo backend|gallery] [--stale-days 21]
  python scripts/agent_skills/backlog_triage.py apply --plan plan.json            # dry run
  python scripts/agent_skills/backlog_triage.py apply --plan plan.json --execute

Plan format (JSON list; each op is validated before anything runs)::

  [
    {"op": "priority", "issue": 328, "to": "p0", "comment": "why",
     "add_labels": ["type:bug"]},
    {"op": "close", "issue": 306, "reason": "completed", "comment": "why"},
    {"op": "stage", "issue": 218, "to": "ready"},
    {"op": "comment", "issue": 227, "body": "..."},
    {"op": "file", "title": "...", "body_file": "body.md",
     "labels": ["type:bug", "priority:p1"], "stage": "ready"}
  ]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backlog_stage as bs  # noqa: E402

PRIORITIES = ("p0", "p1", "p2", "p3")
ACTIVE_STAGES = ("Claimed", "In Progress", "Review", "Blocked")
CLOSE_REASONS = ("completed", "not planned")
OBSOLETE_LABEL = "status:obsolete"

_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issues(states: OPEN, first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title updatedAt
        labels(first: 30) { nodes { name } }
        assignees(first: 5) { nodes { login } }
        projectItems(first: 5) {
          nodes {
            id
            project { number }
            fieldValueByName(name: "Stage") {
              ... on ProjectV2ItemFieldSingleSelectValue { name }
            }
          }
        }
      }
    }
  }
}
"""


class PlanError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def _graphql(repo: str, cursor: str | None) -> dict:
    owner, name = repo.split("/", 1)
    args = ["api", "graphql", "-f", f"query={_QUERY}", "-f", f"owner={owner}", "-f", f"name={name}"]
    if cursor:
        args += ["-f", f"cursor={cursor}"]
    return json.loads(bs.gh_run(*args))["data"]["repository"]["issues"]


def fetch_open_issues(repo: str) -> list[dict]:
    """Open issues flattened to {number, title, labels, priority, stage, item_id, ...}."""
    out: list[dict] = []
    cursor = None
    while True:
        page = _graphql(repo, cursor)
        for n in page["nodes"]:
            out.append(normalize_issue(n))
        if not page["pageInfo"]["hasNextPage"]:
            return out
        cursor = page["pageInfo"]["endCursor"]


def normalize_issue(node: dict) -> dict:
    labels = [lab["name"] for lab in node["labels"]["nodes"]]
    prios = sorted(lab.split(":", 1)[1] for lab in labels if lab.startswith("priority:"))
    item = next((i for i in node["projectItems"]["nodes"]
                 if str(i["project"]["number"]) == str(bs.PROJECT_NUMBER)), None)
    return {
        "number": node["number"],
        "title": node["title"],
        "updated": node["updatedAt"][:10],
        "labels": labels,
        "priorities": prios,
        "priority": prios[0] if prios else None,
        "assignees": [a["login"] for a in node["assignees"]["nodes"]],
        "on_board": item is not None,
        "item_id": item["id"] if item else None,
        "stage": ((item or {}).get("fieldValueByName") or {}).get("name"),
    }


def findings(issues: list[dict], *, stale_days: int, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    cutoff = (today - dt.timedelta(days=stale_days)).isoformat()
    ready = [i for i in issues if i["stage"] == "Ready"]
    ready_prios = {i["priority"] for i in ready}
    lowest_ready = max((p for p in ready_prios if p), default=None)
    by_prio: dict[str, int] = {p: 0 for p in PRIORITIES}
    by_prio["none"] = 0
    for i in issues:
        by_prio[i["priority"] or "none"] += 1

    def nums(pred) -> list[int]:
        return sorted(i["number"] for i in issues if pred(i))

    return {
        "open": len(issues),
        "by_priority": by_prio,
        "ready_by_priority": {p or "none": sum(1 for i in ready if i["priority"] == p)
                              for p in (*PRIORITIES, None)},
        "obsolete_open": nums(lambda i: OBSOLETE_LABEL in i["labels"]),
        "missing_priority": nums(lambda i: not i["priorities"]),
        "multiple_priorities": nums(lambda i: len(i["priorities"]) > 1),
        "not_on_board": nums(lambda i: not i["on_board"]),
        "no_stage": nums(lambda i: i["on_board"] and not i["stage"]),
        "stale_claims": nums(lambda i: i["stage"] in ACTIVE_STAGES[:2] and i["updated"] < cutoff),
        # p0/p1 waiting in Backlog while Ready holds lower-priority work.
        "urgent_not_ready": nums(
            lambda i: i["priority"] in ("p0", "p1")
            and i["stage"] not in ("Ready", *ACTIVE_STAGES)
            and lowest_ready is not None and lowest_ready > i["priority"]
        ),
        "p0": nums(lambda i: i["priority"] == "p0"),
    }


def cmd_snapshot(a) -> dict:
    repo = bs.resolve_repo(a.repo)
    issues = fetch_open_issues(repo)
    result = {"repo": repo, "findings": findings(issues, stale_days=a.stale_days)}
    if not a.findings_only:
        result["issues"] = sorted(issues, key=lambda i: i["number"])
    return result


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def validate_plan(plan: Any) -> list[dict]:
    if not isinstance(plan, list):
        raise PlanError("plan must be a JSON list of ops")
    for idx, op in enumerate(plan):
        where = f"op[{idx}]"
        if not isinstance(op, dict) or "op" not in op:
            raise PlanError(f"{where}: missing 'op'")
        kind = op["op"]
        if kind != "file" and not isinstance(op.get("issue"), int):
            raise PlanError(f"{where}: '{kind}' needs an integer 'issue'")
        if kind == "priority":
            if op.get("to") not in PRIORITIES:
                raise PlanError(f"{where}: 'to' must be one of {PRIORITIES}")
        elif kind == "close":
            if op.get("reason") not in CLOSE_REASONS:
                raise PlanError(f"{where}: 'reason' must be one of {CLOSE_REASONS}")
            if not op.get("comment"):
                raise PlanError(f"{where}: a close needs a 'comment' explaining why")
        elif kind == "stage":
            if op.get("to") not in bs.STAGE_OPTIONS:
                raise PlanError(f"{where}: 'to' must be one of {sorted(bs.STAGE_OPTIONS)}")
        elif kind == "comment":
            if not op.get("body"):
                raise PlanError(f"{where}: 'comment' needs a 'body'")
        elif kind == "file":
            if not op.get("title") or not op.get("body_file"):
                raise PlanError(f"{where}: 'file' needs 'title' and 'body_file'")
            if not Path(op["body_file"]).is_file():
                raise PlanError(f"{where}: body_file not found: {op['body_file']}")
            if op.get("stage") and op["stage"] not in bs.STAGE_OPTIONS:
                raise PlanError(f"{where}: unknown stage {op['stage']!r}")
        else:
            raise PlanError(f"{where}: unknown op {kind!r}")
    return plan


def _item_id(repo: str, number: int) -> str | None:
    owner, name = repo.split("/", 1)
    q = ('{repository(owner:"%s",name:"%s"){issue(number:%d){projectItems(first:5)'
         '{nodes{id project{number}}}}}}' % (owner, name, number))
    nodes = json.loads(bs.gh_run("api", "graphql", "-f", f"query={q}"))[
        "data"]["repository"]["issue"]["projectItems"]["nodes"]
    return next((n["id"] for n in nodes if str(n["project"]["number"]) == str(bs.PROJECT_NUMBER)), None)


def _ensure_item(repo: str, number: int) -> str:
    return _item_id(repo, number) or bs.gh_run(
        "project", "item-add", bs.PROJECT_NUMBER, "--owner", bs.OWNER,
        "--url", f"https://github.com/{repo}/issues/{number}", "--format", "json", "-q", ".id",
    )


def _current_priorities(repo: str, number: int) -> list[str]:
    labels = bs.gh_json("issue", "view", str(number), "--repo", repo, "--json", "labels")["labels"]
    return [lab["name"] for lab in labels if lab["name"].startswith("priority:")]


def describe(op: dict) -> str:
    kind = op["op"]
    if kind == "priority":
        return f"#{op['issue']}: priority -> {op['to']}" + (f" +{op['add_labels']}" if op.get("add_labels") else "")
    if kind == "close":
        return f"#{op['issue']}: close ({op['reason']}) and move to Done"
    if kind == "stage":
        return f"#{op['issue']}: Stage -> {op['to']}"
    if kind == "comment":
        return f"#{op['issue']}: comment"
    return f"file: {op['title']!r}" + (f" -> Stage {op['stage']}" if op.get("stage") else "")


def run_op(repo: str, op: dict) -> str:
    kind, n = op["op"], op.get("issue")
    if kind == "priority":
        args = ["issue", "edit", str(n), "--repo", repo, "--add-label", f"priority:{op['to']}"]
        for old in _current_priorities(repo, n):
            if old != f"priority:{op['to']}":
                args += ["--remove-label", old]
        for extra in op.get("add_labels") or []:
            args += ["--add-label", extra]
        bs.gh_run(*args)
        if op.get("comment"):
            bs.gh_run("issue", "comment", str(n), "--repo", repo, "--body",
                      f"Triage {dt.date.today().isoformat()}: priority -> **{op['to']}**. {op['comment']}")
    elif kind == "close":
        bs.gh_run("issue", "close", str(n), "--repo", repo, "--reason", op["reason"],
                  "--comment", f"Triage {dt.date.today().isoformat()}: {op['comment']}")
        item = _item_id(repo, n)
        if item:
            bs.set_stage(item, "done")
    elif kind == "stage":
        bs.set_stage(_ensure_item(repo, n), op["to"])
    elif kind == "comment":
        bs.gh_run("issue", "comment", str(n), "--repo", repo, "--body", op["body"])
    elif kind == "file":
        args = ["issue", "create", "--repo", repo, "--title", op["title"], "--body-file", op["body_file"]]
        for label in op.get("labels") or []:
            args += ["--label", label]
        url = bs.gh_run(*args).splitlines()[-1]
        number = int(url.rstrip("/").rsplit("/", 1)[1])
        bs.set_stage(_ensure_item(repo, number), op.get("stage") or "backlog")
        return f"filed #{number}"
    return "ok"


def cmd_apply(a) -> dict:
    repo = bs.resolve_repo(a.repo)
    plan = validate_plan(json.loads(Path(a.plan).read_text(encoding="utf-8")))
    ops = [{"op": describe(op)} for op in plan]
    if not a.execute:
        return {"repo": repo, "dry_run": True, "ops": ops}
    done, failed = [], []
    for op, entry in zip(plan, ops):
        try:
            entry["result"] = run_op(repo, op)
            done.append(entry)
        except Exception as exc:  # keep going; report every failure at the end
            entry["error"] = str(exc)[:300]
            failed.append(entry)
    return {"repo": repo, "dry_run": False, "applied": done, "failed": failed}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Backlog priority triage: snapshot the queue, apply a plan.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--repo", default="backend")
    s.add_argument("--stale-days", type=int, default=21)
    s.add_argument("--findings-only", action="store_true")
    ap = sub.add_parser("apply")
    ap.add_argument("--repo", default="backend")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--execute", action="store_true")
    a = p.parse_args(argv)
    try:
        result = cmd_snapshot(a) if a.cmd == "snapshot" else cmd_apply(a)
        ok = not result.get("failed")
    except (PlanError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        result, ok = {"error": str(exc)}, False
    json.dump({"cmd": a.cmd, "ok": ok, **result}, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
