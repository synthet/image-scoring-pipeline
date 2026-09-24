"""Unit tests for scripts/agent_skills/deliver_branch.py (#396). No network, no real git/gh."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agent_skills" / "deliver_branch.py"


@pytest.fixture
def db():
    spec = importlib.util.spec_from_file_location("deliver_branch", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["deliver_branch"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("branch, issue", [
    ("feat/387-localization-shadow", 387),
    ("chore/396-deliver-branch-skill", 396),
    ("fix/bird-bbox-scan-failed-318", 318),
    ("feature/no-number", None),
])
def test_issue_from_branch(db, branch, issue):
    assert db.issue_from_branch(branch) == issue


def test_refuses_to_deliver_master(db, monkeypatch):
    monkeypatch.setattr(db, "current_branch", lambda: "master")
    with pytest.raises(db.DeliverError, match="feature branch"):
        db.cmd_push(argparse.Namespace())


def test_push_refuses_dirty_tree(db, monkeypatch):
    monkeypatch.setattr(db, "current_branch", lambda: "feat/1-x")
    monkeypatch.setattr(db, "git", lambda *a, **k: " M modules/x.py" if a[0] == "status" else "")
    with pytest.raises(db.DeliverError, match="uncommitted"):
        db.cmd_push(argparse.Namespace())


def test_pr_body_must_close_an_issue(db, monkeypatch, tmp_path):
    monkeypatch.setattr(db, "current_branch", lambda: "feat/1-x")
    monkeypatch.setattr(db, "open_pr", lambda _b: None)
    body = tmp_path / "body.md"
    body.write_text("no issue link", encoding="utf-8")
    with pytest.raises(db.DeliverError, match="Closes #"):
        db.cmd_pr(argparse.Namespace(title="t", body_file=str(body)))


def _pr(**kw):
    return {"number": 5, "url": "u", "title": "t", "body": "", "mergeable": "MERGEABLE",
            "isDraft": False, **kw}


@pytest.mark.parametrize("buckets", [["pass", "pending"], ["pass", "fail"], []])
def test_merge_refuses_unless_every_check_is_green(db, monkeypatch, buckets):
    merged = []
    monkeypatch.setattr(db, "current_branch", lambda: "feat/1-x")
    monkeypatch.setattr(db, "open_pr", lambda _b: _pr())
    monkeypatch.setattr(db, "_checks", lambda _n: [{"name": f"c{i}", "bucket": b, "link": ""}
                                                     for i, b in enumerate(buckets)])
    monkeypatch.setattr(db, "gh", lambda *a, **k: merged.append(a) or "")
    with pytest.raises(db.DeliverError, match="not green"):
        db.cmd_merge(argparse.Namespace(method="merge"))
    assert not any(a[:2] == ("pr", "merge") for a in merged)


def test_merge_refuses_draft(db, monkeypatch):
    monkeypatch.setattr(db, "current_branch", lambda: "feat/1-x")
    monkeypatch.setattr(db, "open_pr", lambda _b: _pr(isDraft=True))
    with pytest.raises(db.DeliverError, match="draft"):
        db.cmd_merge(argparse.Namespace(method="merge"))


def test_merge_when_green(db, monkeypatch):
    calls = []
    monkeypatch.setattr(db, "current_branch", lambda: "feat/1-x")
    monkeypatch.setattr(db, "open_pr", lambda _b: _pr())
    monkeypatch.setattr(db, "_checks", lambda _n: [{"name": "a", "bucket": "pass"},
                                                     {"name": "b", "bucket": "skipping"}])
    monkeypatch.setattr(db, "gh", lambda *a, **k: calls.append(("gh",) + a) or "")
    monkeypatch.setattr(db, "git", lambda *a, **k: calls.append(("git",) + a) or "")
    out = db.cmd_merge(argparse.Namespace(method="merge"))
    assert out["merged"] == 5
    assert ("gh", "pr", "merge", "5", "--merge") in calls
    assert ("git", "push", "origin", "--delete", "feat/1-x") in calls


_PORCELAIN = """worktree /repo
HEAD abc
branch refs/heads/master

worktree /repo/.agent/scratch/wt-1
HEAD def
branch refs/heads/feat/1-x
"""


def test_worktree_holding_finds_master(db, monkeypatch):
    monkeypatch.setattr(db, "git", lambda *a, **k: _PORCELAIN)
    assert db._worktree_holding("master") == Path("/repo")
    assert db._worktree_holding("feat/1-x") == Path("/repo/.agent/scratch/wt-1")
    assert db._worktree_holding("other") is None


def test_sync_master_fast_forwards_only_in_the_holding_worktree(db, monkeypatch):
    calls = []

    def _git(*a, cwd=None, check=True):
        calls.append((a, cwd))
        if a[:2] == ("worktree", "list"):
            return _PORCELAIN
        if a[0] == "rev-parse":
            return "abc1234"
        return ""

    monkeypatch.setattr(db, "git", _git)
    out = db.cmd_sync_master(argparse.Namespace())
    assert (("pull", "--ff-only", "origin", "master"), Path("/repo")) in calls
    assert not any(a[0] in ("reset", "rebase") for a, _ in calls)
    assert out["updated_in"] == str(Path("/repo"))


def test_sync_master_moves_ref_when_not_checked_out(db, monkeypatch):
    calls = []

    def _git(*a, cwd=None, check=True):
        calls.append(a)
        if a[:2] == ("worktree", "list"):
            return "worktree /repo\nHEAD abc\nbranch refs/heads/feat/1-x\n"
        return "abc1234" if a[0] == "rev-parse" else ""

    monkeypatch.setattr(db, "git", _git)
    assert db.cmd_sync_master(argparse.Namespace())["updated_in"] == "ref only"
    assert ("fetch", "origin", "master:master") in calls


def test_main_reports_errors_as_json_with_nonzero_exit(db, monkeypatch, capsys):
    monkeypatch.setattr(db, "current_branch", lambda: "master")
    assert db.main(["push"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "feature branch" in out["error"]
