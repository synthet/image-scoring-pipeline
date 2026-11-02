"""CLI round trips via cli.main (no subprocess)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("yaml")

from modules.vexlum import cli  # noqa: E402
from modules.vexlum.worker import handle_line  # noqa: E402


def _run(capsys, argv):
    code = cli.main(argv)
    return code, capsys.readouterr().out


def test_search_human_output(capsys):
    code, out = _run(capsys, ["search", "error", "summary", "--limit", "2"])
    assert code == 0
    assert "diagnostics.get_error_summary" in out


def test_resolve_json(capsys):
    code, out = _run(capsys, ["--json", "resolve", "db.query"])
    assert code == 0
    assert json.loads(out)["tier"] == "read"


def test_exec_dry_run_destructive_gives_token(capsys):
    code, out = _run(capsys, ["--json", "exec", "DELETE /api/images/{image_id}", "--args", '{"image_id": 1}',
                              "--dry-run"])
    assert code == 0
    data = json.loads(out)
    assert data["action_id"] == "api.images.delete_image"
    assert data["data"]["confirm_token"]


def test_exec_error_exit_code(capsys):
    code, out = _run(capsys, ["exec", "api.tagging.stop_tagging"])
    assert code == 1
    assert "confirmation_required" in out


def test_exec_bad_args_is_usage_error(capsys):
    assert cli.main(["exec", "db.query", "--args", "[1]"]) == 2


def test_list_by_source(capsys):
    code, out = _run(capsys, ["list", "--source", "db"])
    assert code == 0
    assert "db.execute" in out and "3 actions" in out


def test_worker_line_protocol():
    out = handle_line('{"id": "r1", "tool": "resolve", "args": {"action_id": "db.schema"}}')
    assert out["_request_id"] == "r1"
    assert out["action_id"] == "db.schema"
    assert handle_line("not json")["code"] == "invalid_json"
    assert handle_line('{"id": "r2"}')["code"] == "missing_tool"
