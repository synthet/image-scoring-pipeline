"""Job lifecycle regression coverage through the public database facade."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from modules import db


class RecordingConnector:
    def __init__(self):
        self.row = {
            "id": 17,
            "status": "running",
            "current_phase": "indexing",
            "next_phase_index": 0,
            "runner_state": "running",
            "log": "existing log",
            "phase_id": 7,
            "job_type": "pipeline",
        }
        self.phases = [{"phase_code": "indexing", "phase_order": 0, "state": "running"}]
        self.writes = []
        self.queries = []
        self.committed = False
        self.returning = [{"id": 17}]

    def query_one(self, sql, params=None):
        self.queries.append((sql, params))
        if "COUNT(*)" in sql:
            return {"cnt": len(self.phases)}
        if "FROM pipeline_phases" in sql:
            return {"code": "indexing"}
        return dict(self.row) if self.row else None

    def execute(self, sql, params):
        self.writes.append((sql, params))

    def execute_returning(self, sql, params):
        self.execute(sql, params)
        return self.returning

    def run_transaction(self, operation):
        result = operation(self)
        self.committed = True
        return result


@pytest.fixture
def lifecycle(monkeypatch):
    conn = RecordingConnector()
    audit = SimpleNamespace(
        record_audit=Mock(),
        build_insert_patch=lambda fields: fields,
        build_field_update_patch=lambda field, old, new: {field: (old, new)},
    )
    callbacks = SimpleNamespace(
        connector=conn,
        audit=audit,
        event=Mock(),
        broadcast=Mock(),
        verify=Mock(return_value=None),
        sync=Mock(return_value="indexing"),
        phase_write=Mock(),
        next_phase=Mock(return_value="metadata"),
        phase_id=Mock(return_value=7),
        release=Mock(),
        reconcile=Mock(return_value=0),
        post_audit=Mock(),
    )
    monkeypatch.setattr(db, "get_connector", lambda: conn)
    monkeypatch.setattr(db, "audit", audit)
    monkeypatch.setattr(db, "record_pipeline_event", callbacks.event)
    monkeypatch.setattr(db.event_manager, "broadcast_threadsafe", callbacks.broadcast)
    monkeypatch.setattr(db, "get_phase_id", callbacks.phase_id)
    monkeypatch.setattr(
        db, "_strict_verify_resolved_ids_terminal_for_phase", callbacks.verify
    )
    monkeypatch.setattr(db, "_resolve_multi_phase_job_phases_sync_code", callbacks.sync)
    monkeypatch.setattr(db, "set_job_phase_state", callbacks.phase_write)
    monkeypatch.setattr(db, "get_job_phases", lambda job_id, tx=None: conn.phases)
    monkeypatch.setattr(db, "get_next_running_job_phase", callbacks.next_phase)
    monkeypatch.setattr(
        db, "reconcile_stale_running_phases_for_jobs", callbacks.reconcile
    )
    monkeypatch.setattr(
        db, "run_post_completion_data_quality_audit", callbacks.post_audit
    )
    monkeypatch.setattr(
        "modules.phase_work_claims.release_claims_for_job", callbacks.release
    )
    return callbacks


@pytest.mark.parametrize(
    "status", ["completed", "failed", "canceled", "cancelled", "interrupted"]
)
def test_terminal_status_commits_before_notifications_and_cleanup(lifecycle, status):
    conn = lifecycle.connector
    lifecycle.audit.record_audit.side_effect = lambda *args, **kwargs: (
        pytest.fail("audit happened before commit") if not conn.committed else None
    )
    db.update_job_status(17, status, log="result")

    expected = "cancelled" if status == "canceled" else status
    sql, params = conn.writes[0]
    assert "finished_at = ?" in sql and "completed_at = ?" in sql
    assert params[0] == expected
    assert params[1] == params[2]
    assert params[3:] == ("result", "indexing", 0, "running", 17)
    lifecycle.broadcast.assert_called_once_with(
        f"job_{expected}",
        {
            "job_id": 17,
            "status": expected,
            "current_phase": "indexing",
            "next_phase_index": 0,
            "runner_state": "running",
            "job_type": "pipeline",
        },
    )
    lifecycle.release.assert_called_once_with(17)
    lifecycle.reconcile.assert_called_once_with(
        [17],
        error_message=f"{db.STALE_RUNNING_RECONCILED_MSG}:job_{expected}",
        in_flight_to="not_started" if status == "interrupted" else "failed",
    )
    assert lifecycle.post_audit.call_count == (status == "completed")
    assert lifecycle.verify.call_count == (status == "completed")


@pytest.mark.parametrize("status", ["paused", "running", "restarting"])
def test_nonterminal_status_preserves_or_overrides_cursor_without_cleanup(
    lifecycle, status
):
    db.update_job_status(
        17, status, current_phase="metadata", next_phase_index=1, runner_state="waiting"
    )
    sql, params = lifecycle.connector.writes[0]
    assert "finished_at" not in sql
    if status == "running":
        assert "started_at = COALESCE(started_at, ?)" in sql
    assert params[-4:] == ("metadata", 1, "waiting", 17)
    lifecycle.release.assert_not_called()
    lifecycle.reconcile.assert_not_called()
    lifecycle.post_audit.assert_not_called()


@pytest.mark.parametrize("missing", [False, True])
def test_rejected_transaction_has_no_status_side_effects(lifecycle, missing):
    if missing:
        lifecycle.connector.row = None
        message = "Job not found"
    else:
        lifecycle.connector.row["status"] = "completed"
        message = "Invalid job status transition"
    with pytest.raises(ValueError, match=message):
        db.update_job_status(17, "running")
    assert lifecycle.connector.writes == []
    assert not lifecycle.connector.committed
    lifecycle.audit.record_audit.assert_not_called()
    lifecycle.event.assert_not_called()
    lifecycle.broadcast.assert_not_called()
    lifecycle.release.assert_not_called()


@pytest.mark.parametrize(
    "log, expected",
    [(None, "unfinished images"), ("worker log", "worker log\nunfinished images")],
)
def test_strict_completion_failure_becomes_failed_and_retains_log(
    lifecycle, log, expected
):
    lifecycle.verify.return_value = "unfinished images"
    db.update_job_status(17, " COMPLETED ", log=log)
    params = lifecycle.connector.writes[0][1]
    assert params[0] == "failed" and params[3] == expected
    lifecycle.phase_write.assert_called_once_with(
        17, "indexing", "failed", error_message=expected, tx=lifecycle.connector
    )
    assert lifecycle.event.call_args.kwargs["severity"] == "error"
    assert lifecycle.event.call_args.kwargs["critical"] is True
    lifecycle.post_audit.assert_not_called()


@pytest.mark.parametrize("next_state", ["queued", "running"])
def test_stage_completion_keeps_multiphase_job_running(lifecycle, next_state):
    conn = lifecycle.connector
    conn.phases = [
        {"phase_code": "indexing", "phase_order": 0, "state": "running"},
        {"phase_code": "metadata", "phase_order": 1, "state": next_state},
    ]
    lifecycle.phase_write.side_effect = lambda *args, **kwargs: conn.phases[0].update(
        state="completed"
    )
    db.update_job_status(17, "completed")
    sql, params = conn.writes[0]
    assert "status = 'running'" in sql
    assert "finished_at = NULL, completed_at = NULL" in sql
    assert params == ("existing log", "metadata", 1, 7, 17)
    assert lifecycle.broadcast.call_args.args[0] == "job_running"
    lifecycle.sync.assert_called_once_with(17, "completed", tx=conn)
    lifecycle.phase_id.assert_called_once_with("metadata")
    lifecycle.release.assert_not_called()
    lifecycle.reconcile.assert_not_called()
    lifecycle.post_audit.assert_not_called()


@pytest.mark.parametrize("runner_state", [None, "settled"])
def test_final_stage_completion_marks_multiphase_job_terminal(lifecycle, runner_state):
    conn = lifecycle.connector
    conn.phases = [
        {"phase_code": "indexing", "phase_order": 0, "state": "skipped"},
        {"phase_code": "metadata", "phase_order": 1, "state": "running"},
    ]
    lifecycle.sync.return_value = "metadata"
    lifecycle.phase_write.side_effect = lambda *args, **kwargs: conn.phases[1].update(
        state="completed"
    )
    db.update_job_status(17, "completed", runner_state=runner_state)
    params = conn.writes[0][1]
    assert params[0] == "completed"
    assert params[3] == "existing log"
    assert params[-2] == (runner_state or "completed")
    lifecycle.release.assert_called_once_with(17)
    lifecycle.post_audit.assert_called_once_with(17)


def test_phase_sync_failure_does_not_undo_job_status(lifecycle):
    lifecycle.phase_write.side_effect = RuntimeError("phase sync unavailable")
    db.update_job_status(17, "paused")
    assert lifecycle.connector.committed
    assert lifecycle.broadcast.call_args.args[0] == "job_paused"


def test_terminal_cleanup_failure_does_not_prevent_remaining_hooks(lifecycle):
    lifecycle.release.side_effect = RuntimeError("claims unavailable")
    lifecycle.reconcile.side_effect = RuntimeError("reconciliation unavailable")
    db.update_job_status(17, "completed")
    assert lifecycle.connector.committed
    lifecycle.reconcile.assert_called_once()
    lifecycle.post_audit.assert_called_once_with(17)


@pytest.mark.parametrize("legacy_type", [None, "pipeline"])
def test_create_job_preserves_payload_phase_mapping_and_telemetry(
    lifecycle, legacy_type
):
    result = db.create_job(
        "/images",
        phase_code="indexing",
        job_type=legacy_type,
        queue_payload={"image_ids": [1, 2]},
        description="test scope",
    )
    assert result == 17
    params = lifecycle.connector.writes[0][1]
    assert params[:4] == ("/images", 7, legacy_type or "indexing", "pending")
    assert params[4] == params[8]
    assert json.loads(params[9]) == {"image_ids": [1, 2]}
    assert params[10] == "test scope"
    assert lifecycle.audit.record_audit.call_args.kwargs["source"] == "db.create_job"
    assert lifecycle.event.call_args.kwargs["metadata"]["description"] == "test scope"


def test_update_log_does_not_change_status_or_emit_status_hooks(lifecycle):
    db.update_job_log(17, "new log")
    assert lifecycle.connector.writes == [
        ("UPDATE jobs SET log = ? WHERE id = ?", ("new log", 17))
    ]
    assert lifecycle.connector.committed
    lifecycle.event.assert_not_called()
    lifecycle.broadcast.assert_not_called()


def test_update_log_rejects_missing_job(lifecycle):
    lifecycle.connector.row = None
    with pytest.raises(ValueError, match="Job not found: 17"):
        db.update_job_log(17, "new log")
    assert lifecycle.connector.writes == []


def test_cursor_update_persists_exact_values_and_emits_phase_transition(lifecycle):
    db.set_job_execution_cursor(17, "metadata", 1, "waiting")
    assert lifecycle.connector.writes[0][1] == ("metadata", 1, "waiting", 17)
    assert lifecycle.event.call_args.kwargs["category"] == "phase-transition"
    assert lifecycle.event.call_args.kwargs["metadata"] == {
        "current_phase": "metadata",
        "next_phase_index": 1,
        "runner_state": "waiting",
    }


def test_facade_resolves_replaced_connector_on_each_call(lifecycle, monkeypatch):
    assert db.get_job(17)["status"] == "running"
    replacement = RecordingConnector()
    replacement.row = None
    monkeypatch.setattr(db, "get_connector", lambda: replacement)
    assert db.get_job(17) is None
    assert len(replacement.queries) == 1


def test_continuation_query_retains_phase_preference_and_pipeline_exclusion(lifecycle):
    assert db.get_running_job_for_phase_continuation()["id"] == 17
    sql = lifecycle.connector.queries[0][0]
    assert "j.job_type != 'ui_pipeline'" in sql
    assert "CASE jp.state WHEN 'running' THEN 0 ELSE 1 END" in sql
    assert "jp.phase_order ASC" in sql
