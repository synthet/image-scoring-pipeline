"""
Tests for SelectionRunner phase-aware completion logic.

Validates that when a selection job has multiple phases (e.g. culling + bird_species),
the runner completes only the culling phase and enqueues a follow-up job for remaining
phases instead of bulk-completing everything.
"""

import json
import threading
import pytest
from unittest.mock import patch, MagicMock, call


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


def test_bulk_completed_allowed_when_all_started():
    """_resolve_multi_phase returns __bulk_completed__ when all phases have started_at."""
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "bird_species", "state": "running", "started_at": "2026-03-24T00:01:00"},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        result = _resolve_multi_phase_job_phases_sync_code(999, "completed")

    assert result == "__bulk_completed__"


def test_bulk_completed_allowed_when_skipped_unstarted():
    """Phases that are already skipped/completed don't block bulk completion."""
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "bird_species", "state": "skipped", "started_at": None},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        result = _resolve_multi_phase_job_phases_sync_code(999, "completed")

    assert result == "__bulk_completed__"


# ──────────────────────────────────────────────────────────────────────────────
# SelectionRunner._complete_phase_and_advance
# ──────────────────────────────────────────────────────────────────────────────

def test_selection_runner_enqueues_bird_species():
    """When culling finishes and bird_species phase is pending, a follow-up job should be enqueued."""
    from modules.selection_runner import SelectionRunner

    runner = SelectionRunner()
    log_messages = []

    phases_after_culling = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00", "completed_at": "2026-03-24T00:01:00"},
        {"phase_code": "bird_species", "state": "pending", "started_at": None, "completed_at": None},
    ]

    with patch("modules.selection_runner.db") as mock_db, \
         patch("modules.selection_runner.event_manager") as mock_em:
        mock_db.get_job_phases.return_value = phases_after_culling
        mock_db.enqueue_job.return_value = (500, 1)  # follow-up job_id, position

        runner._complete_phase_and_advance(449, "/mnt/d/Photos/test", log_messages.append)

    # Should have set culling phase to completed
    mock_db.set_job_phase_state.assert_any_call(449, "culling", "completed")

    # Should have enqueued a bird_species job
    mock_db.enqueue_job.assert_called_once()
    enqueue_args = mock_db.enqueue_job.call_args
    assert enqueue_args[1].get("job_type") == "bird_species" or enqueue_args[0][2] == "bird_species"

    # Should have created job phases for the follow-up job
    mock_db.create_job_phases.assert_called_once_with(500, ["bird_species"], first_phase_state="queued")

    # Should have completed the parent job
    mock_db.update_job_status.assert_called_once_with(449, "completed")

    # Log should mention advancing
    assert any("bird_species" in msg for msg in log_messages)


def test_selection_runner_no_followup_when_no_remaining():
    """When culling is the only phase, just complete the job normally."""
    from modules.selection_runner import SelectionRunner

    runner = SelectionRunner()

    phases_only_culling = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00", "completed_at": "2026-03-24T00:01:00"},
    ]

    with patch("modules.selection_runner.db") as mock_db, \
         patch("modules.selection_runner.event_manager"):
        mock_db.get_job_phases.return_value = phases_only_culling

        runner._complete_phase_and_advance(449, "/mnt/d/Photos/test", lambda msg: None)

    # Should NOT have enqueued any follow-up job
    mock_db.enqueue_job.assert_not_called()

    # Should have completed the job
    mock_db.update_job_status.assert_called_once_with(449, "completed")
