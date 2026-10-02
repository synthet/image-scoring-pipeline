"""Queue and job control contracts exercised through the database facade."""

import datetime
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from modules import db


class FixedDatetime(datetime.datetime):
    @classmethod
    def now(cls):
        return cls(2026, 10, 2, 12, 0)


@pytest.fixture
def queue(monkeypatch):
    conn = Mock()
    conn.query.return_value = []
    conn.query_one.return_value = None
    conn.execute.return_value = 1
    conn.execute_returning.return_value = [{"id": 37}]
    conn.committed = False

    def transaction(operation):
        result = operation(conn)
        conn.committed = True
        return result

    conn.run_transaction.side_effect = transaction
    factory = Mock(return_value=conn)
    phase_id = Mock(return_value=7)
    by_id = Mock(return_value={"id": 37, "status": "running"})
    resume = Mock()
    monkeypatch.setattr(db, "get_connector", factory)
    monkeypatch.setattr(db, "get_phase_id", phase_id)
    monkeypatch.setattr(db, "get_job_by_id", by_id)
    monkeypatch.setattr(db, "resume_job_phases", resume)
    monkeypatch.setattr(datetime, "datetime", FixedDatetime)
    return SimpleNamespace(
        conn=conn, factory=factory, phase_id=phase_id, by_id=by_id, resume=resume
    )


@pytest.mark.parametrize(
    "payload",
    [None, {"scope": "/scope"}, '{"target_scope":"/scope"}', "invalid json", [1, 2]],
)
def test_enqueue_retains_payload_and_dense_position(queue, monkeypatch, payload):
    priority = Mock(return_value=350)
    monkeypatch.setattr("modules.job_priority.resolve_job_enqueue_priority", priority)
    queue.conn.query.return_value = [{"cnt": 3}]
    assert db.enqueue_job(
        "/images",
        phase_code="scoring",
        queue_payload=payload,
        description="scope reason",
    ) == (37, 3)
    params = queue.conn.execute_returning.call_args.args[1]
    assert params[:3] == ("/images", 7, "scoring")
    assert params[3] == params[4] == FixedDatetime.now()
    expected_json = (
        payload
        if isinstance(payload, str)
        else json.dumps(payload)
        if payload is not None
        else None
    )
    assert params[5] == expected_json
    assert params[6:] == (
        350,
        "/scope"
        if isinstance(payload, dict) or payload == '{"target_scope":"/scope"}'
        else "/images",
        "scope reason",
    )
    decoded = (
        payload
        if isinstance(payload, dict)
        else {"target_scope": "/scope"}
        if payload == '{"target_scope":"/scope"}'
        else {}
    )
    priority.assert_called_once_with(decoded, job_type="scoring")
    queue.conn.execute.assert_called_once_with(
        "UPDATE jobs SET queue_position = ? WHERE id = ?", (37, 37)
    )
    assert queue.conn.query.call_args.args[1] == (37,)
    assert queue.conn.committed


def test_enqueue_without_returned_id_does_not_write_queue_position(queue):
    queue.conn.execute_returning.return_value = []
    assert db.enqueue_job("/images") == (None, 0)
    queue.conn.execute.assert_not_called()
    assert not queue.conn.committed


def test_enqueue_unexpected_error_is_not_silenced(queue):
    queue.conn.execute_returning.side_effect = ValueError("invalid database input")
    with pytest.raises(ValueError, match="invalid database input"):
        db.enqueue_job("/images")


@pytest.mark.parametrize("row, affected", [(None, 1), ({"id": 37}, 0), ({"id": 37}, 1)])
def test_dequeue_claims_job_conditionally_and_reads_it_after_commit(
    queue, row, affected
):
    queue.conn.query_one.return_value = row
    queue.conn.execute.return_value = affected
    queue.by_id.side_effect = lambda job_id: {
        "id": job_id,
        "committed": queue.conn.committed,
    }
    result = db.dequeue_next_job()
    sql = queue.conn.query_one.call_args.args[0]
    assert "COALESCE(cancel_requested, 0) = 0" in sql
    assert "COALESCE(priority, 100) DESC, COALESCE(queue_position, id) ASC" in sql
    if row and affected:
        assert result == {"id": 37, "committed": True}
        update_sql, params = queue.conn.execute.call_args.args
        assert "status = 'queued' AND COALESCE(cancel_requested, 0) = 0" in update_sql
        assert params == (FixedDatetime.now(), 37)
        queue.by_id.assert_called_once_with(37)
    else:
        assert result is None
        queue.by_id.assert_not_called()
        if not row:
            queue.conn.execute.assert_not_called()


@pytest.mark.parametrize("status", ["paused", "interrupted", "failed"])
def test_requeue_resets_execution_fields_and_returns_dense_position(queue, status):
    queue.conn.query_one.side_effect = [{"status": status}, {"count": 2}]
    assert db.requeue_job(37) == (37, 2)
    sql, params = queue.conn.execute.call_args.args
    assert "started_at = NULL" in sql and "finished_at = NULL" in sql
    assert "completed_at = NULL" in sql and "cancel_requested = 0" in sql
    assert "runner_state = NULL" in sql and "current_phase = NULL" in sql
    assert params == (FixedDatetime.now(), 37, 37)
    assert queue.conn.committed


@pytest.mark.parametrize(
    "status", ["running", "completed", "cancelled", "queued", "unknown"]
)
def test_requeue_rejects_states_without_queued_transition(queue, status):
    queue.conn.query_one.return_value = {"status": status}
    with pytest.raises(ValueError, match="Cannot requeue"):
        db.requeue_job(37)
    queue.conn.execute.assert_not_called()
    assert not queue.conn.committed


def test_requeue_uses_current_facade_transition_policy(queue, monkeypatch):
    queue.conn.query_one.side_effect = [{"status": "custom"}, {"COUNT(*)": 1}]
    monkeypatch.setattr(db, "JOB_ALLOWED_TRANSITIONS", {"custom": {"queued"}})
    assert db.requeue_job(37) == (37, 1)


@pytest.mark.parametrize(
    "status, reason",
    [
        ("completed", "already_finished"),
        ("failed", "already_finished"),
        ("cancelled", "already_finished"),
        ("running", "running_not_supported"),
        ("interrupted", "not_cancellable_state"),
        ("pending", "not_cancellable_state"),
    ],
)
def test_cancel_rejects_unsupported_states_without_writes(queue, status, reason):
    queue.conn.query_one.return_value = {"status": status}
    assert db.request_cancel_job(37) == {
        "success": False,
        "reason": reason,
        "status": status,
    }
    queue.conn.execute.assert_not_called()


@pytest.mark.parametrize("status", ["queued", "paused"])
def test_cancel_eligible_job_sets_terminal_timestamps_and_clears_queue_key(
    queue, status
):
    queue.conn.query_one.return_value = {"status": status}
    assert db.request_cancel_job(37) == {
        "success": True,
        "reason": "cancelled",
        "status": status,
    }
    sql, params = queue.conn.execute.call_args.args
    assert "status = 'cancelled', cancel_requested = 1, queue_position = NULL" in sql
    assert "WHERE id = ? AND status IN ('queued', 'paused')" in sql
    assert params == (FixedDatetime.now(), FixedDatetime.now(), 37)


@pytest.mark.parametrize(
    "latest, reason",
    [
        ("running", "running_not_supported"),
        ("completed", "already_finished"),
        ("failed", "already_finished"),
        ("cancelled", "already_finished"),
        (None, "not_found"),
        ("queued", "cancel_failed"),
    ],
)
def test_cancel_rechecks_state_after_losing_update_race(queue, latest, reason):
    queue.conn.query_one.side_effect = [
        {"status": "queued"},
        {"status": latest} if latest else None,
    ]
    queue.conn.execute.return_value = 0
    expected = {"success": False, "reason": reason}
    if latest:
        expected["status"] = latest
    assert db.request_cancel_job(37) == expected
    assert queue.conn.query_one.call_count == 2


def test_cancel_missing_job_returns_not_found(queue):
    assert db.request_cancel_job(37) == {"success": False, "reason": "not_found"}
    queue.conn.execute.assert_not_called()


@pytest.mark.parametrize("affected", [0, 1])
def test_failed_job_restart_resumes_phases_only_after_successful_write(queue, affected):
    queue.conn.execute.return_value = affected
    assert db.restart_failed_job(37) == {"success": bool(affected)}
    sql = queue.conn.execute.call_args.args[0]
    assert "retry_count = COALESCE(retry_count, 0) + 1" in sql
    assert "WHERE id = ? AND status = 'failed'" in sql
    if affected:
        queue.resume.assert_called_once_with(37)
    else:
        queue.resume.assert_not_called()


@pytest.mark.parametrize(
    "priority, expected", [(-4, 1), (2000, 999), ("150", 150), (None, 100)]
)
def test_set_priority_clamps_input_and_targets_only_queued_or_paused(
    queue, priority, expected
):
    assert db.set_job_priority(37, priority) == {"success": True, "priority": expected}
    sql, params = queue.conn.execute.call_args.args
    assert "status IN ('queued', 'paused')" in sql
    assert params == (expected, 37)


@pytest.mark.parametrize("function", ["adjust_job_priority", "bump_job_priority"])
@pytest.mark.parametrize("affected", [0, 1])
def test_priority_adjustment_preserves_bounds_and_missing_update_result(
    queue, function, affected
):
    queue.conn.execute.return_value = affected
    queue.conn.query_one.return_value = {"priority": 120}
    assert getattr(db, function)(37, "invalid") == {
        "success": bool(affected),
        "priority": 120 if affected else None,
    }
    sql, params = queue.conn.execute.call_args.args
    assert "< 1 THEN 1" in sql and "> 999 THEN 999" in sql
    assert params == (10, 10, 10, 37)
    assert queue.conn.query_one.call_count == affected


def test_pause_targets_only_queued_jobs(queue):
    assert db.pause_queue_job(37) == {"success": True}
    sql, params = queue.conn.execute.call_args.args
    assert "WHERE id = ? AND status = 'queued'" in sql
    assert params == (FixedDatetime.now(), 37)


def test_update_payload_preserves_pre_serialized_value(queue):
    db.update_job_payload(37, '{"scope":"/images"}')
    queue.conn.execute.assert_called_once_with(
        "UPDATE jobs SET queue_payload = ? WHERE id = ?", ('{"scope":"/images"}', 37)
    )


@pytest.mark.parametrize("limit", [0, -1])
def test_queue_listing_with_nonpositive_limit_does_not_connect(queue, limit):
    assert db.get_queued_jobs(limit=limit) == []
    queue.factory.assert_not_called()


def test_queue_listing_formats_dense_positions_eta_and_related_job_fields(queue):
    queue.conn.query.return_value = [
        {
            "id": 1,
            "status": "queued",
            "queue_position": 100,
            "input_path": "/one",
            "job_type": "scoring",
        },
        {
            "id": 2,
            "status": "paused",
            "queue_position": 200,
            "phase_name": "Metadata",
            "target_scope": "/two",
            "priority": 350,
            "retry_count": 2,
        },
        {
            "id": 3,
            "status": "failed",
            "selected_phases": "indexing, metadata",
            "dependency_blockers": "keywords",
        },
    ]
    queue.conn.query_one.return_value = {"avg_sec": 60}
    rows = db.get_queued_jobs(limit=5000, include_related=True)
    assert queue.conn.query.call_args.args[1] == (1, 1000)
    assert [row["queue_position"] for row in rows] == [1, 2, "-"]
    assert [row["estimated_start"] for row in rows] == [
        "2026-10-02 12:00:00",
        "2026-10-02 12:01:00",
        "-",
    ]
    assert [row["target_scope"] for row in rows] == ["/one", "/two", "-"]
    assert [row["selected_phases"] for row in rows] == [
        "scoring",
        "Metadata",
        "indexing, metadata",
    ]
    assert rows[0]["priority"] == 100 and rows[0]["retry_count"] == 0
    assert rows[2]["dependency_blockers"] == "keywords"


def test_queue_listing_uses_default_eta_when_duration_query_fails(queue):
    queue.conn.query.return_value = [{"status": "queued"}, {"status": "queued"}]
    queue.conn.query_one.side_effect = RuntimeError("duration unavailable")
    rows = db.get_queued_jobs(limit="invalid")
    assert queue.conn.query.call_args.args[1] == (0, 200)
    assert rows[1]["estimated_start"] == "2026-10-02 12:02:00"


@pytest.mark.parametrize(
    "function", ["get_queued_jobs_count", "count_running_pipeline_jobs"]
)
def test_background_job_counts_tolerate_connector_failure(queue, function):
    queue.factory.side_effect = RuntimeError("database unavailable")
    assert getattr(db, function)() == 0


def test_running_count_can_include_maintenance(queue):
    queue.conn.query_one.return_value = {"cnt": 3}
    assert db.count_running_pipeline_jobs(exclude_maintenance=False) == 3
    assert "maintenance" not in queue.conn.query_one.call_args.args[0]


def test_active_folder_lookup_matches_windows_and_wsl_forms(queue):
    queue.conn.query.return_value = [{"id": 37, "input_path": "/mnt/d/Photos/one"}]
    assert db.find_active_job_for_folder("D:\\Photos\\one", job_type="scoring") == 37
    sql, params = queue.conn.query.call_args.args
    assert "AND job_type = ?" in sql
    assert params == (*db._ACTIVE_JOB_STATUSES, "scoring")


def test_active_folder_lookup_uses_current_facade_status_policy(queue, monkeypatch):
    monkeypatch.setattr(db, "_ACTIVE_JOB_STATUSES", ("custom",))
    assert db.find_active_job_for_folder("/images") is None
    assert queue.conn.query.call_args.args[1] == ("custom",)


def test_empty_folder_lookup_does_not_connect(queue):
    assert db.find_active_job_for_folder("") is None
    queue.factory.assert_not_called()
