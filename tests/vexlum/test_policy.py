"""Tier policy and confirm tokens."""

from __future__ import annotations

import pytest

from modules.mcp.actions.errors import ConfirmationRequiredError, PolicyError
from modules.vexlum import policy


def _rec(tier: str) -> dict:
    return {"action_id": f"x.{tier}", "tier": tier}


def test_read_runs_without_confirmation():
    policy.check(_rec("read"), {}, dry_run=False, confirmed=False, confirm_token=None)


def test_write_needs_confirmed():
    with pytest.raises(ConfirmationRequiredError):
        policy.check(_rec("write"), {}, dry_run=False, confirmed=False, confirm_token=None)
    policy.check(_rec("write"), {}, dry_run=False, confirmed=True, confirm_token=None)


def test_dry_run_always_allowed():
    for tier in policy.TIERS:
        policy.check(_rec(tier), {}, dry_run=True, confirmed=False, confirm_token=None)


def test_destructive_needs_env_then_token(monkeypatch):
    rec = _rec("destructive")
    args = {"query": "DELETE FROM t"}
    with pytest.raises(ConfirmationRequiredError):
        policy.check(rec, args, dry_run=False, confirmed=False, confirm_token=None)
    with pytest.raises(PolicyError) as exc:
        policy.check(rec, args, dry_run=False, confirmed=True, confirm_token=None)
    assert exc.value.details.get("policy") == "elevated_env"

    monkeypatch.setenv(policy.ELEVATED_ENV, "1")
    with pytest.raises(policy.ConfirmTokenError):
        policy.check(rec, args, dry_run=False, confirmed=True, confirm_token=None)
    token = policy.issue_token(rec["action_id"], args)["confirm_token"]
    policy.check(rec, args, dry_run=False, confirmed=True, confirm_token=token)


def test_token_bound_to_args_and_action():
    token = policy.issue_token("db.execute", {"query": "A"})["confirm_token"]
    policy.verify_token("db.execute", {"query": "A"}, token)
    with pytest.raises(policy.ConfirmTokenError):
        policy.verify_token("db.execute", {"query": "B"}, token)
    with pytest.raises(policy.ConfirmTokenError):
        policy.verify_token("db.other", {"query": "A"}, token)
    with pytest.raises(policy.ConfirmTokenError):
        policy.verify_token("db.execute", {"query": "A"}, "garbage")


def test_token_expires():
    issued = policy.issue_token("a", {}, now=1000.0)
    policy.verify_token("a", {}, issued["confirm_token"], now=1000.0 + policy.TOKEN_TTL_SECONDS - 1)
    with pytest.raises(policy.ConfirmTokenError):
        policy.verify_token("a", {}, issued["confirm_token"], now=1000.0 + policy.TOKEN_TTL_SECONDS + 1)


def test_token_survives_process_via_key_file(tmp_path, monkeypatch):
    monkeypatch.delenv("VEXLUM_TOKEN_SECRET", raising=False)
    monkeypatch.setenv("VEXLUM_TOKEN_KEY_FILE", str(tmp_path / "k"))
    policy.reset_token_key_cache()
    token = policy.issue_token("a", {"x": 1})["confirm_token"]
    policy.reset_token_key_cache()  # simulate a new CLI process
    policy.verify_token("a", {"x": 1}, token)
    assert (tmp_path / "k").exists()


def test_requirements_shape():
    assert policy.requirements("read") == {"confirmed": False, "confirm_token": False, "env": None}
    assert policy.requirements("destructive")["env"] == "VEXLUM_ALLOW_ELEVATED=1"
