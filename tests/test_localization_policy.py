"""Localization new-images-only scope and claim reuse (#527). No database.

The real boundary and run-history SQL is exercised in
``tests/integration/test_localization_enablement_e2e.py`` (``-m postgres``).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from modules import localization as loc
from modules import localization_policy as policy
from modules.job_dispatcher import JobDispatcher


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------

def test_flag_defaults_protect_the_legacy_library():
    assert loc.new_images_only({}) is True
    assert loc.repair_enabled({}) is False


def test_flags_read_their_keys():
    assert loc.new_images_only({"new_images_only": False}) is False
    assert loc.repair_enabled({"repair": {"enabled": True}}) is True


# ---------------------------------------------------------------------------
# filter_auto_eligible
# ---------------------------------------------------------------------------

@pytest.fixture
def connector(monkeypatch):
    conn = MagicMock()
    conn.query_one.return_value = {"enabled_at": "2026-10-04 00:00:00"}
    monkeypatch.setattr("modules.db.get_connector", lambda: conn, raising=False)
    return conn


def _row(image_id, *, new=False, source_hash=None, version="size-mtime-head-1"):
    return {"id": image_id, "file_path": f"/p/{image_id}.nef", "is_new": new,
            "source_hash": source_hash, "source_hash_version": version}


def test_filter_keeps_new_and_source_changed_drops_unchanged_legacy(connector, monkeypatch):
    connector.query.return_value = [
        _row(1, new=True),                       # indexed after the boundary
        _row(2),                                 # legacy, never localized
        _row(3, source_hash="old"),              # legacy, file changed
        _row(4, source_hash="same"),             # legacy, file unchanged
        _row(5, source_hash=None),               # legacy import / outage run: no hash
    ]
    monkeypatch.setattr(
        "modules.rendition.source_identity",
        lambda path: ("same", "size-mtime-head-1"),
    )

    assert policy.filter_auto_eligible([5, 4, 3, 2, 1]) == [3, 1]


def test_filter_treats_hash_version_change_as_changed(connector, monkeypatch):
    connector.query.return_value = [_row(7, source_hash="h", version="older-rule")]
    monkeypatch.setattr("modules.rendition.source_identity", lambda path: ("h", "size-mtime-head-1"))

    assert policy.filter_auto_eligible([7]) == [7]


def test_filter_unreadable_file_is_not_a_change(connector, monkeypatch):
    connector.query.return_value = [_row(8, source_hash="h")]

    def _missing(path):
        raise FileNotFoundError(path)

    monkeypatch.setattr("modules.rendition.source_identity", _missing)

    assert policy.filter_auto_eligible([8]) == []


def test_filter_writes_boundary_insert_if_absent(connector):
    connector.query.return_value = []
    policy.filter_auto_eligible([1])

    sql = connector.execute.call_args.args[0]
    assert "INSERT INTO localization_enablement" in sql and "ON CONFLICT" in sql


def test_filter_empty_input_touches_nothing(connector):
    assert policy.filter_auto_eligible([]) == []
    connector.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Dispatcher wiring
# ---------------------------------------------------------------------------

def test_auto_scope_passthrough_when_flag_off(monkeypatch):
    monkeypatch.setattr(loc, "localization_config", lambda: {"new_images_only": False})
    with patch("modules.localization_policy.filter_auto_eligible") as f:
        assert JobDispatcher._localization_auto_scope([1, 2]) == [1, 2]
    f.assert_not_called()


def test_auto_scope_filters_when_flag_on(monkeypatch):
    monkeypatch.setattr(loc, "localization_config", lambda: {})
    with patch("modules.localization_policy.filter_auto_eligible", return_value=[2]) as f:
        assert JobDispatcher._localization_auto_scope([1, 2]) == [2]
    f.assert_called_once_with([1, 2])


@patch("modules.phase_work_claims.mark_claims_running")
@patch("modules.phase_work_claims.claim_image_phases")
def test_explicit_ids_dispatch_only_what_this_job_claimed(mock_claim, mock_running):
    mock_claim.return_value = {"claimed": [1], "skipped_already_claimed": [2]}

    assert JobDispatcher._claim_explicit_ids(9, "localization", [1, 2]) == [1]
    mock_claim.assert_called_once_with(9, "localization", [1, 2])
    mock_running.assert_called_once_with(9, "localization", [1])


@patch("modules.phase_work_claims.mark_claims_running")
@patch("modules.phase_work_claims.claim_image_phases")
def test_explicit_ids_all_claimed_elsewhere_marks_nothing(mock_claim, mock_running):
    mock_claim.return_value = {"claimed": [], "skipped_already_claimed": [1]}

    assert JobDispatcher._claim_explicit_ids(9, "localization", [1]) == []
    mock_running.assert_not_called()
