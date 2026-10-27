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


# ---------------------------------------------------------------------------
# Bounded repair: repair_state
# ---------------------------------------------------------------------------

_ID = ("cfg-a", "src-1", "size-mtime-head-1")


def _run(status="retryable_error", age=0.0, error_code="detect_error", ident=_ID):
    cfg, src, ver = ident
    return {"status": status, "error_code": error_code, "age_seconds": age,
            "detector_config_hash": cfg, "source_hash": src, "source_hash_version": ver}


def test_no_history_or_success_is_not_limited():
    assert policy.repair_state([]) == policy.RepairState()
    assert not policy.repair_state([_run(status="detected", error_code=None)]).blocked


def test_backoff_one_minute_after_first_failure():
    assert policy.repair_state([_run(age=10)]).wait_seconds == pytest.approx(50)
    assert not policy.repair_state([_run(age=61)]).blocked


def test_backoff_five_minutes_after_second_failure():
    state = policy.repair_state([_run(age=100), _run(age=500)])
    assert state.attempts == 2 and state.wait_seconds == pytest.approx(200)
    assert not policy.repair_state([_run(age=301), _run(age=900)]).blocked


def test_third_failure_exhausts():
    state = policy.repair_state([_run(age=10_000)] * 3)
    assert state.exhausted and state.blocked


def test_success_ends_the_streak():
    history = [_run(age=5), _run(status="no_detection", error_code=None), _run(), _run()]
    assert policy.repair_state(history).attempts == 1


def test_identity_change_inside_history_ends_the_streak():
    history = [_run(), _run(ident=("cfg-old", "src-1", "size-mtime-head-1")), _run()]
    assert policy.repair_state(history).attempts == 1


def test_changed_next_identity_starts_over():
    history = [_run(age=10_000)] * 3
    assert policy.repair_state(history, _ID).exhausted
    assert policy.repair_state(history, ("cfg-a", "src-2", "size-mtime-head-1")) == policy.RepairState()
    assert policy.repair_state(history, ("cfg-b", "src-1", "size-mtime-head-1")) == policy.RepairState()


def test_detector_outage_never_counts():
    outage = _run(error_code="detector_unavailable", ident=("unavailable", None, None))
    assert policy.repair_state([outage] * 5) == policy.RepairState()
    # Outage rows between two real failures neither count nor break the streak.
    assert policy.repair_state([_run(age=400), outage, outage, _run()]).attempts == 2


# ---------------------------------------------------------------------------
# Runner: deferral and dispatcher flag
# ---------------------------------------------------------------------------

def test_runner_defers_exhausted_and_cooling(monkeypatch):
    from modules.localization_runner import LocalizationRunner

    monkeypatch.setattr("modules.localization_runner.source_identity", lambda p: _ID[1:])
    ctx = loc.DetectorContext(enabled=True, config_hash="cfg-a")

    assert LocalizationRunner._repair_deferral([_run(age=10_000)] * 3, "/p", ctx) == "exhausted"
    assert LocalizationRunner._repair_deferral([_run(age=5)], "/p", ctx) == "cooling_down"
    assert LocalizationRunner._repair_deferral([_run(age=120)], "/p", ctx) is None
    # A new detector config is a new artifact identity.
    ctx_b = loc.DetectorContext(enabled=True, config_hash="cfg-b")
    assert LocalizationRunner._repair_deferral([_run(age=10_000)] * 3, "/p", ctx_b) is None


def test_runner_unreadable_file_uses_empty_source_identity(monkeypatch):
    from modules.localization_runner import LocalizationRunner

    def _missing(path):
        raise FileNotFoundError(path)

    monkeypatch.setattr("modules.localization_runner.source_identity", _missing)
    ctx = loc.DetectorContext(enabled=True, config_hash="cfg-a")
    history = [_run(age=10_000, ident=("cfg-a", None, None))] * 3
    assert LocalizationRunner._repair_deferral(history, "/gone", ctx) == "exhausted"
