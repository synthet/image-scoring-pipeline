"""WEBUI_LOCK_FILE is inert by default (UI E2E live tier, #769).

webui.py imports Gradio at module level, so the helper is extracted with ast instead of importing
the module; the test then runs in any environment.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

WEBUI = Path(__file__).resolve().parents[1] / "webui.py"


def _lock_path_fn():
    tree = ast.parse(WEBUI.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_webui_lock_path")
    namespace: dict = {"os": os}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(WEBUI), "exec"), namespace)  # noqa: S102
    return namespace["_webui_lock_path"]


def test_default_is_webui_lock_in_the_working_directory(monkeypatch):
    monkeypatch.delenv("WEBUI_LOCK_FILE", raising=False)
    assert _lock_path_fn()() == "webui.lock"


def test_blank_override_keeps_the_default(monkeypatch):
    monkeypatch.setenv("WEBUI_LOCK_FILE", "   ")
    assert _lock_path_fn()() == "webui.lock"


def test_override_is_used(monkeypatch):
    monkeypatch.setenv("WEBUI_LOCK_FILE", "/tmp/ui-e2e/webui.lock")
    assert _lock_path_fn()() == "/tmp/ui-e2e/webui.lock"


def test_main_writes_the_lock_through_the_helper():
    assert "lock_file = _webui_lock_path()" in WEBUI.read_text(encoding="utf-8")
