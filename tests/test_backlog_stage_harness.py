"""Unit tests for scripts/agent_skills/backlog_stage.py (#725). No network, no real gh."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "agent_skills"
DENIED = "GraphQL: Resource not accessible by personal access token (updateProjectV2ItemFieldValue)"


@pytest.fixture
def bs(monkeypatch):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("backlog_stage", SCRIPTS / "backlog_stage.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["backlog_stage"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    return mod


class FakeGh:
    """Records each gh call and its env token; answers from a list of (rc, stdout, stderr)."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, cmd, **kwargs):
        env = kwargs.get("env")
        token = None if env is not None and "GITHUB_TOKEN" not in env else "env"
        self.calls.append((cmd[1:], token))
        rc, out, err = self.replies.pop(0)
        return subprocess.CompletedProcess(cmd, rc, out, err)


def _install(bs, monkeypatch, replies):
    fake = FakeGh(replies)
    monkeypatch.setattr(bs.subprocess, "run", fake)
    return fake


def test_project_write_retries_without_env_token(bs, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    fake = _install(bs, monkeypatch, [(1, "", DENIED), (0, "ok", "")])
    assert bs.gh_run("project", "item-edit", "--id", "I") == "ok"
    assert [t for _a, t in fake.calls] == ["env", None]


@pytest.mark.parametrize(
    ("token", "args", "err"),
    [
        (None, ("project", "item-edit"), DENIED),  # no env token to drop
        ("x", ("issue", "edit", "1"), DENIED),  # not a board call
        ("x", ("project", "item-edit"), "GraphQL: Could not resolve to a node"),  # other error
    ],
)
def test_no_retry_outside_the_pat_denied_board_case(bs, monkeypatch, token, args, err):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    if token:
        monkeypatch.setenv("GITHUB_TOKEN", token)
    else:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    fake = _install(bs, monkeypatch, [(1, "", err)])
    with pytest.raises(RuntimeError):
        bs.gh_run(*args)
    assert len(fake.calls) == 1


def test_add_puts_issue_on_board_and_sets_stage(bs, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    issue = {"number": 7, "state": "OPEN", "assignees": [], "title": "t",
             "url": "https://github.com/synthet/image-scoring-gallery/issues/7"}
    fake = _install(bs, monkeypatch, [
        (0, json.dumps(issue), ""),
        (0, json.dumps({"id": "PVTI_7"}), ""),
        (0, "", ""),
    ])
    result = bs.add_issue(7, "gallery", "done")
    assert result.ok and result.item_id == "PVTI_7" and result.stage == "done"
    add_args, edit_args = fake.calls[1][0], fake.calls[2][0]
    assert add_args[:2] == ["project", "item-add"] and issue["url"] in add_args
    assert edit_args[:2] == ["project", "item-edit"] and bs.STAGE_OPTIONS["done"] in edit_args


def test_add_dry_run_makes_no_board_call(bs, monkeypatch):
    issue = {"number": 7, "title": "t", "url": "u"}
    fake = _install(bs, monkeypatch, [(0, json.dumps(issue), "")])
    result = bs.add_issue(7, "backend", dry_run=True)
    assert result.ok and result.stage == "backlog" and "dry_run" in result.message
    assert len(fake.calls) == 1
