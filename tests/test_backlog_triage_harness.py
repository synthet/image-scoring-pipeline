"""Unit tests for scripts/agent_skills/backlog_triage.py (#400). No network, no real gh."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "agent_skills"


@pytest.fixture
def bt():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("backlog_triage", SCRIPTS / "backlog_triage.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["backlog_triage"] = mod
    spec.loader.exec_module(mod)
    return mod


def _node(number, labels=(), stage=None, on_board=True, updated="2026-09-20", project=1):
    items = []
    if on_board:
        items.append({"id": f"PVTI_{number}", "project": {"number": project},
                      "fieldValueByName": {"name": stage} if stage else None})
    return {
        "number": number, "title": f"issue {number}", "updatedAt": f"{updated}T00:00:00Z",
        "labels": {"nodes": [{"name": lab} for lab in labels]},
        "assignees": {"nodes": []},
        "projectItems": {"nodes": items},
    }


def test_normalize_reads_stage_from_project_1_only(bt):
    issue = bt.normalize_issue(_node(5, ["priority:p1"], stage="Ready", project=2))
    assert issue["on_board"] is False and issue["stage"] is None
    issue = bt.normalize_issue(_node(5, ["priority:p1"], stage="Ready"))
    assert issue["on_board"] and issue["stage"] == "Ready" and issue["priority"] == "p1"


def test_findings_flag_every_category(bt):
    issues = [bt.normalize_issue(n) for n in (
        _node(1, ["priority:p3", "status:obsolete"], stage="Backlog"),
        _node(2, [], stage="Backlog"),                                     # no priority
        _node(3, ["priority:p1", "priority:p2"], stage="Backlog"),         # two priorities
        _node(4, ["priority:p2"], on_board=False),                         # off board
        _node(5, ["priority:p2"], stage=None),                             # no Stage
        _node(6, ["priority:p2"], stage="Claimed", updated="2026-07-01"),  # stale claim
        _node(7, ["priority:p0"], stage="Backlog"),                        # urgent, not Ready
        _node(8, ["priority:p3"], stage="Ready"),
        _node(9, ["priority:p1"], stage="In Progress", updated="2026-09-22"),  # fresh, active
    )]
    f = bt.findings(issues, stale_days=21, today=dt.date(2026, 9, 23))
    assert f["obsolete_open"] == [1]
    assert f["missing_priority"] == [2]
    assert f["multiple_priorities"] == [3]
    assert f["not_on_board"] == [4]
    assert f["no_stage"] == [5]
    assert f["stale_claims"] == [6]
    assert f["urgent_not_ready"] == [3, 7]
    assert f["p0"] == [7]
    assert f["ready_by_priority"]["p3"] == 1 and f["by_priority"]["none"] == 1


def test_urgent_not_ready_is_empty_when_ready_holds_only_higher_work(bt):
    issues = [bt.normalize_issue(n) for n in (
        _node(1, ["priority:p1"], stage="Backlog"),
        _node(2, ["priority:p0"], stage="Ready"),
    )]
    assert bt.findings(issues, stale_days=21)["urgent_not_ready"] == []


@pytest.mark.parametrize("plan, message", [
    ({"op": "priority"}, "JSON list"),
    ([{"issue": 1}], "missing 'op'"),
    ([{"op": "priority", "issue": "1", "to": "p1"}], "integer 'issue'"),
    ([{"op": "priority", "issue": 1, "to": "urgent"}], "'to' must be one of"),
    ([{"op": "close", "issue": 1, "reason": "dup", "comment": "x"}], "'reason'"),
    ([{"op": "close", "issue": 1, "reason": "completed"}], "needs a 'comment'"),
    ([{"op": "stage", "issue": 1, "to": "someday"}], "'to' must be one of"),
    ([{"op": "file", "title": "t", "body_file": "/no/such/file.md"}], "body_file not found"),
    ([{"op": "delete", "issue": 1}], "unknown op"),
])
def test_validate_plan_rejects_bad_ops(bt, plan, message):
    with pytest.raises(bt.PlanError, match=message):
        bt.validate_plan(plan)


def test_apply_is_a_dry_run_without_execute(bt, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(bt.bs, "gh_run", lambda *a: calls.append(a) or "")
    monkeypatch.setattr(bt.bs, "set_stage", lambda *a: calls.append(a))
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps([
        {"op": "priority", "issue": 3, "to": "p1", "comment": "why"},
        {"op": "close", "issue": 4, "reason": "completed", "comment": "fixed in v1"},
        {"op": "stage", "issue": 5, "to": "ready"},
    ]), encoding="utf-8")
    out = bt.cmd_apply(argparse.Namespace(repo="backend", plan=str(plan), execute=False))
    assert out["dry_run"] is True and len(out["ops"]) == 3
    assert calls == []


def test_priority_op_swaps_the_old_label(bt, monkeypatch):
    calls = []
    monkeypatch.setattr(bt, "_current_priorities", lambda _r, _n: ["priority:p2"])
    monkeypatch.setattr(bt.bs, "gh_run", lambda *a: calls.append(a) or "")
    bt.run_op("synthet/x", {"op": "priority", "issue": 3, "to": "p0", "add_labels": ["type:bug"]})
    edit = calls[0]
    assert "--add-label" in edit and "priority:p0" in edit
    assert edit[edit.index("--remove-label") + 1] == "priority:p2"
    assert "type:bug" in edit
    assert len(calls) == 1  # no comment requested


def test_close_moves_card_to_done(bt, monkeypatch):
    stages = []
    monkeypatch.setattr(bt.bs, "gh_run", lambda *a: "")
    monkeypatch.setattr(bt, "_item_id", lambda _r, _n: "PVTI_9")
    monkeypatch.setattr(bt.bs, "set_stage", lambda item, key: stages.append((item, key)))
    bt.run_op("synthet/x", {"op": "close", "issue": 9, "reason": "not planned", "comment": "obsolete"})
    assert stages == [("PVTI_9", "done")]


def test_execute_reports_failures_and_keeps_going(bt, tmp_path, monkeypatch):
    def _run_op(_repo, op):
        if op["issue"] == 1:
            raise RuntimeError("boom")
        return "ok"

    monkeypatch.setattr(bt, "run_op", _run_op)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps([{"op": "stage", "issue": 1, "to": "ready"},
                                {"op": "stage", "issue": 2, "to": "ready"}]), encoding="utf-8")
    out = bt.cmd_apply(argparse.Namespace(repo="backend", plan=str(plan), execute=True))
    assert len(out["applied"]) == 1 and len(out["failed"]) == 1
    assert "boom" in out["failed"][0]["error"]
