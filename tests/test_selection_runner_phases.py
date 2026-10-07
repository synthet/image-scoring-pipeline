"""
Tests for SelectionRunner phase-aware completion logic.

Validates that when a selection job has multiple phases (e.g. culling + bird_species),
the runner completes only the culling phase and enqueues a follow-up job for remaining
phases instead of bulk-completing everything.
"""

import json
from unittest.mock import patch

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# _resolve_multi_phase_job_phases_sync_code — safety net
# ──────────────────────────────────────────────────────────────────────────────

def test_bulk_completed_blocked_when_unstarted_phases():
    """_resolve_multi_phase should NOT return __bulk_completed__ when phases have never started."""
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "culling", "state": "running", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "bird_species", "state": "pending", "started_at": None},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        result = _resolve_multi_phase_job_phases_sync_code(999, "completed")

    # Should NOT bulk-complete; should return the running phase
    assert result != "__bulk_completed__"
    assert result == "culling"


def test_completed_prefers_running_phase_when_all_have_started_at():
    """When a later phase is running, complete that row — never bulk-complete all phases."""
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "bird_species", "state": "running", "started_at": "2026-03-24T00:01:00"},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        result = _resolve_multi_phase_job_phases_sync_code(999, "completed")

    assert result == "bird_species"


def test_completed_returns_none_when_all_phases_already_terminal():
    """No phase row to sync when everything is already completed or skipped."""
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "bird_species", "state": "skipped", "started_at": None},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        result = _resolve_multi_phase_job_phases_sync_code(999, "completed")

    assert result is None


def test_resolve_empty_phases_returns_none():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    with patch("modules.db.get_job_phases", return_value=[]):
        assert _resolve_multi_phase_job_phases_sync_code(1, "completed") is None


def test_resolve_single_phase_row_returns_none():
    """Multi-phase logic only applies when there are 2+ job_phases rows."""
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "scoring", "state": "running", "started_at": "2026-03-24T00:00:00"},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "completed") is None


def test_running_prefers_existing_running_row():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "indexing", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "scoring", "state": "running", "started_at": "2026-03-24T00:01:00"},
        {"phase_code": "keywords", "state": "pending", "started_at": None},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "running") == "scoring"


def test_running_maps_to_first_queued_when_none_running():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "indexing", "state": "queued", "started_at": None},
        {"phase_code": "scoring", "state": "pending", "started_at": None},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "running") == "indexing"


def test_running_fallback_first_row_when_no_running_or_queued():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "alpha", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "beta", "state": "completed", "started_at": "2026-03-24T00:01:00"},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "running") == "alpha"


def test_completed_non_terminal_without_unstarted_row():
    """started_at set on a later phase but state not terminal — still pick that phase."""
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {
            "phase_code": "bird_species",
            "state": "queued",
            "started_at": "2026-03-24T00:01:00",
        },
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "completed") == "bird_species"


def test_completed_all_terminal_treats_cancelled_spelling():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "bird_species", "state": "cancelled", "started_at": None},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "completed") is None


def test_failed_prefers_running_phase():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "scoring", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "keywords", "state": "running", "started_at": "2026-03-24T00:01:00"},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "failed") == "keywords"


def test_failed_returns_last_phase_when_none_running():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "a", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "b", "state": "completed", "started_at": "2026-03-24T00:01:00"},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "interrupted") == "b"


def test_resolve_misc_job_status_returns_none():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "x", "state": "queued", "started_at": None},
        {"phase_code": "y", "state": "pending", "started_at": None},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "queued") is None
        assert _resolve_multi_phase_job_phases_sync_code(1, "paused") is None


# ──────────────────────────────────────────────────────────────────────────────
# SelectionRunner._complete_phase_and_advance: durable delegation (#368).

def _phase_row(code, state):
    return {"phase_code": code, "state": state}


def _advance(phases, result=(500, 1), error=None, payload=None, plan_error=None, payload_error=None):
    from modules.selection_runner import SelectionRunner
    with patch("modules.selection_runner.db") as mock_db, patch("modules.selection_runner.event_manager") as events:
        mock_db.get_job_phases.return_value = phases
        mock_db.get_job_phases.side_effect = plan_error
        mock_db.get_connector.return_value.query_one.return_value = {"queue_payload": payload or {}}
        mock_db.get_connector.return_value.query_one.side_effect = payload_error
        mock_db.enqueue_delegated_followup.return_value = result
        mock_db.enqueue_delegated_followup.side_effect = error
        messages = []
        SelectionRunner()._complete_phase_and_advance(449, "/test/photos", lambda message, *args: messages.append(message))
    return mock_db, events, messages


def test_successful_handoff_leaves_completion_to_child():
    mock_db, events, _ = _advance([_phase_row("culling", "running"), _phase_row("bird_species", "pending")])
    assert mock_db.enqueue_delegated_followup.call_args.args == (449, "/test/photos", ["bird_species"])
    mock_db.update_job_status.assert_not_called()
    mock_db.set_job_phase_state.assert_not_called()
    events.broadcast_threadsafe.assert_not_called()


def test_all_remaining_phases_are_delegated_in_order():
    mock_db, _, _ = _advance([
        _phase_row("culling", "running"), _phase_row("keywords", "queued"), _phase_row("bird_species", "pending"),
    ])
    assert mock_db.enqueue_delegated_followup.call_args.args[2] == ["keywords", "bird_species"]


def test_culling_only_completes_without_a_child():
    mock_db, events, _ = _advance([_phase_row("culling", "running")])
    mock_db.enqueue_delegated_followup.assert_not_called()
    mock_db.set_job_phase_state.assert_called_once_with(449, "culling", "completed")
    mock_db.update_job_status.assert_called_once_with(449, "completed")
    assert events.broadcast_threadsafe.call_args.args[1]["status"] == "completed"


@pytest.mark.parametrize("result,error", [((None, 0), None), ((500, 1), RuntimeError("queue unavailable")), ((500, 1), RuntimeError("phase plan write failed"))])
def test_atomic_handoff_failure_keeps_culling_success_but_fails_parent(result, error):
    mock_db, events, _ = _advance([
        _phase_row("culling", "running"), _phase_row("bird_species", "pending"),
    ], result=result, error=error)
    mock_db.set_job_phase_state.assert_called_once_with(449, "culling", "completed")
    assert mock_db.update_job_status.call_args.args[1] == "failed"
    message = mock_db.update_job_status.call_args.args[2]
    assert "bird_species" in message and "did not run" in message
    if error:
        assert str(error) in message
    assert events.broadcast_threadsafe.call_args.args[1]["status"] == "failed"


def test_handoff_preserves_flags_scope_and_audit_reason():
    payload = {"generate_captions": True, "custom_keywords": ["eagle"], "overwrite": False,
               "scope_paths": ["/a", "/b"], "resolved_image_ids": [1],
               "resolved_image_ids_by_stage": {"keywords": [2, 3], "bird_species": [4]}}
    mock_db, _, _ = _advance([
        _phase_row("culling", "running"), _phase_row("keywords", "pending"), _phase_row("bird_species", "pending"),
    ], payload=json.dumps(payload))
    child_payload = mock_db.enqueue_delegated_followup.call_args.kwargs["queue_payload"]
    for key in ("generate_captions", "custom_keywords", "overwrite", "scope_paths", "resolved_image_ids_by_stage"):
        assert child_payload[key] == payload[key]
    assert child_payload["parent_job_id"] == 449
    assert child_payload["resolved_image_ids"] == [2, 3]
    assert child_payload["target_phases"] == ["keywords", "bird_species"]
    assert child_payload["reason"]["criteria"]["enqueued_phases"] == ["keywords", "bird_species"]


def test_handoff_does_not_reuse_culling_image_ids_for_next_phase():
    mock_db, _, _ = _advance([
        _phase_row("culling", "running"), _phase_row("keywords", "pending"),
    ], payload={"resolved_image_ids": [1]})
    assert "resolved_image_ids" not in mock_db.enqueue_delegated_followup.call_args.kwargs["queue_payload"]


@pytest.mark.parametrize("error_key", ["plan_error", "payload_error"])
def test_handoff_read_failure_cannot_silently_complete_or_lose_requested_flags(error_key):
    mock_db, _, _ = _advance([
        _phase_row("culling", "running"), _phase_row("keywords", "pending"),
    ], **{error_key: RuntimeError("database unavailable")})
    mock_db.enqueue_delegated_followup.assert_not_called()
    assert mock_db.update_job_status.call_args.args[1] == "failed"
    assert "database unavailable" in mock_db.update_job_status.call_args.args[2]
