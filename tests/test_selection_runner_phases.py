"""
Tests for SelectionRunner phase-aware completion logic.

Validates that when a selection job has multiple phases (e.g. culling + bird_species),
the runner completes only the culling phase and enqueues a follow-up job for remaining
phases instead of bulk-completing everything.
"""

import json
from unittest.mock import call, patch


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
# SelectionRunner._complete_phase_and_advance
#
# Delegation contract (issue #346, localization rollout stage 1): culling runs its
# own phase, hands *every* remaining phase to one follow-up job, and marks the
# delegated parent rows `skipped` with a "delegated to job #N" note.  They are not
# marked `completed` — the parent never ran that work.
# ──────────────────────────────────────────────────────────────────────────────

def _phase_row(code: str, state: str, *, started: str | None = None, completed: str | None = None) -> dict:
    return {
        "phase_code": code,
        "state": state,
        "started_at": started,
        "completed_at": completed,
    }


_CULLING_DONE = _phase_row(
    "culling", "completed",
    started="2026-03-24T00:00:00", completed="2026-03-24T00:01:00",
)


def _advance(job_phases, *, enqueue_return=(500, 1), enqueue_side_effect=None, job_id=449):
    """Run ``_complete_phase_and_advance`` against a mocked db; return (mock_db, log_messages)."""
    from modules.selection_runner import SelectionRunner

    runner = SelectionRunner()
    log_messages: list[str] = []

    with patch("modules.selection_runner.db") as mock_db,          patch("modules.selection_runner.event_manager"):
        mock_db.get_job_phases.return_value = job_phases
        if enqueue_side_effect is not None:
            mock_db.enqueue_job.side_effect = enqueue_side_effect
        else:
            mock_db.enqueue_job.return_value = enqueue_return

        runner._complete_phase_and_advance(job_id, "/mnt/d/Photos/test", log_messages.append)

    return mock_db, log_messages


def test_selection_runner_enqueues_bird_species():
    """Culling finishes with bird_species pending -> a follow-up job is enqueued."""
    mock_db, log_messages = _advance([
        _CULLING_DONE,
        _phase_row("bird_species", "pending"),
    ])

    # The runner's own phase really did run.
    mock_db.set_job_phase_state.assert_any_call(449, "culling", "completed")

    mock_db.enqueue_job.assert_called_once()
    enqueue_args = mock_db.enqueue_job.call_args
    assert enqueue_args[1].get("job_type") == "bird_species"

    mock_db.create_job_phases.assert_called_once_with(
        500, ["bird_species"], first_phase_state="queued",
    )
    mock_db.update_job_status.assert_called_once_with(449, "completed")
    assert any("bird_species" in msg for msg in log_messages)


def test_parent_delegated_phase_marked_skipped_with_note():
    """The delegated parent row is terminal, but records the hand-off rather than claiming work.

    Marking it `completed` (the pre-#346 behaviour) asserted that bird_species had
    finished while the child job was still sitting in the queue, so a run that later
    failed outright still reported every stage green.  `skipped` is terminal too — the
    Runs UI still shows the parent finished — but the error_message says where the work
    actually went.  ``job_phases.state`` has no CHECK constraint (migration 0014
    deliberately excluded one) and `skipped` is already written by
    ``pipeline_orchestrator``.
    """
    mock_db, _ = _advance(
        [_CULLING_DONE, _phase_row("bird_species", "pending")],
        enqueue_return=(501, 1),
    )

    phase_state_calls = mock_db.set_job_phase_state.call_args_list
    assert call(449, "culling", "completed") in phase_state_calls
    assert call(
        449, "bird_species", "skipped", error_message="delegated to job #501",
    ) in phase_state_calls
    assert call(449, "bird_species", "completed") not in phase_state_calls


def test_selection_runner_hands_all_remaining_phases_to_one_child():
    """A culling -> keywords -> bird_species plan must not strand bird_species.

    The pre-#346 code passed only ``remaining[0]`` to ``create_job_phases``, so the
    child job was created with keywords alone and bird_species was silently dropped —
    no job was ever enqueued for it.
    """
    mock_db, log_messages = _advance([
        _CULLING_DONE,
        _phase_row("keywords", "pending"),
        _phase_row("bird_species", "pending"),
    ], enqueue_return=(600, 1))

    # One child job, entered at the first remaining phase.
    mock_db.enqueue_job.assert_called_once()
    assert mock_db.enqueue_job.call_args[1].get("job_type") == "keywords"

    # ...carrying BOTH downstream phases.
    mock_db.create_job_phases.assert_called_once_with(
        600, ["keywords", "bird_species"], first_phase_state="queued",
    )

    phase_state_calls = mock_db.set_job_phase_state.call_args_list
    for code in ("keywords", "bird_species"):
        assert call(
            449, code, "skipped", error_message="delegated to job #600",
        ) in phase_state_calls

    assert any("bird_species" in msg for msg in log_messages)


def test_followup_records_every_enqueued_phase_in_the_run_reason():
    """The audit trail names all delegated phases, not just the entry one."""
    mock_db, _ = _advance([
        _CULLING_DONE,
        _phase_row("keywords", "pending"),
        _phase_row("bird_species", "pending"),
    ], enqueue_return=(601, 1))

    payload = mock_db.enqueue_job.call_args[1]["queue_payload"]
    blob = json.dumps(payload, default=str)
    assert "keywords" in blob and "bird_species" in blob


def test_selection_runner_no_followup_when_no_remaining():
    """When culling is the only phase, just complete the job normally."""
    mock_db, _ = _advance([_CULLING_DONE])

    mock_db.enqueue_job.assert_not_called()
    mock_db.create_job_phases.assert_not_called()
    mock_db.update_job_status.assert_called_once_with(449, "completed")


def test_enqueue_returning_no_job_id_does_not_mark_parent_phase_terminal():
    """A failed hand-off must not look like completed work.

    ``enqueue_job`` returning ``None`` means no child exists.  The delegated rows stay
    non-terminal so the run still reads as unfinished instead of silently reporting a
    stage that nothing will ever run.
    """
    mock_db, _ = _advance(
        [_CULLING_DONE, _phase_row("bird_species", "pending")],
        enqueue_return=(None, None),
    )

    mock_db.create_job_phases.assert_not_called()
    codes = [c.args[1] for c in mock_db.set_job_phase_state.call_args_list]
    assert "bird_species" not in codes
    # The runner's own phase is still legitimately completed.
    assert codes == ["culling"]


def test_enqueue_raising_does_not_mark_parent_phase_terminal():
    """Same invariant when ``enqueue_job`` raises instead of returning None."""
    mock_db, _ = _advance(
        [_CULLING_DONE, _phase_row("bird_species", "pending")],
        enqueue_side_effect=RuntimeError("queue unavailable"),
    )

    mock_db.create_job_phases.assert_not_called()
    codes = [c.args[1] for c in mock_db.set_job_phase_state.call_args_list]
    assert codes == ["culling"]


def test_running_phase_other_than_culling_is_also_delegated():
    """``remaining`` covers pending, queued and running rows alike."""
    mock_db, _ = _advance([
        _CULLING_DONE,
        _phase_row("keywords", "queued"),
        _phase_row("bird_species", "running", started="2026-03-24T00:02:00"),
    ], enqueue_return=(700, 1))

    mock_db.create_job_phases.assert_called_once_with(
        700, ["keywords", "bird_species"], first_phase_state="queued",
    )
