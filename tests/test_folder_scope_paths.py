"""Unit tests for scope folder listing (Selection vs phase summary alignment)."""

from unittest.mock import MagicMock

import pytest


def test_list_folder_paths_under_scope_uses_canonical_root_and_descendants(monkeypatch):
    from modules import db

    monkeypatch.setattr(db, "get_or_create_folder", lambda p: 99)

    connector = MagicMock()
    connector.query_one.return_value = {"path": "/mnt/d/Photos/project"}
    connector.query.return_value = [
        {"path": "/mnt/d/Photos/project"},
        {"path": "/mnt/d/Photos/project/sub"},
    ]
    monkeypatch.setattr(db, "get_connector", lambda: connector)

    out = db.list_folder_paths_under_scope("/mnt/d/Photos/project")
    assert out == ["/mnt/d/Photos/project", "/mnt/d/Photos/project/sub"]

    connector.query_one.assert_called_once()
    _sql, params = connector.query.call_args[0]
    assert params[0] == "/mnt/d/Photos/project"
    assert params[1] == "/mnt/d/Photos/project/%"


def test_list_folder_paths_under_scope_empty_input():
    from modules import db

    assert db.list_folder_paths_under_scope("") == []
    assert db.list_folder_paths_under_scope("   ") == []


def test_list_folder_paths_under_scope_no_folder_row(monkeypatch):
    from modules import db

    monkeypatch.setattr(db, "get_or_create_folder", lambda p: None)
    assert db.list_folder_paths_under_scope("/mnt/d/x") == []


def test_list_folder_paths_under_scope_missing_path_column(monkeypatch):
    from modules import db

    monkeypatch.setattr(db, "get_or_create_folder", lambda p: 1)
    connector = MagicMock()
    connector.query_one.return_value = {}
    monkeypatch.setattr(db, "get_connector", lambda: connector)
    assert db.list_folder_paths_under_scope("/mnt/d/x") == []
