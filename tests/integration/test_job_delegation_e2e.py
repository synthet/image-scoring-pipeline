"""Durable culling handoff and recovery, against the isolated PostgreSQL database."""

import importlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from modules import db

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def _clean(postgres_test_session, clean_postgres):
    yield


def handoff():
    parent = db.create_job(
        "/delegation/test", phase_code="culling", job_type="selection", status="running",
    )
    db.create_job_phases(parent, ["culling", "keywords", "bird_species"])
    child, _ = db.enqueue_delegated_followup(
        parent, "/delegation/test", ["keywords", "bird_species"],
        queue_payload={"generate_captions": True}, description="delegation test",
    )
    return parent, child


def states(job_id):
    return {p["phase_code"]: p["state"] for p in db.get_job_phases(job_id)}


def finish_child(child):
    db.update_job_status(child, "running")
    db.update_job_status(child, "completed")
    db.update_job_status(child, "completed")


def test_waiting_parent_is_unfinished_and_does_not_consume_dispatch_capacity():
    parent, child = handoff()
    row = db.get_job(parent)
    assert row["status"] == "running"
    assert row["runner_state"] == "waiting_child"
    assert row["completed_at"] is None
    assert states(parent) == {"culling": "completed", "keywords": "queued", "bird_species": "pending"}
    assert db.get_job(child)["parent_job_id"] == parent
    assert db.count_running_pipeline_jobs() == 0
    assert db.get_running_job_for_phase_continuation() is None
    assert db.dequeue_next_job()["id"] == child
    assert db.count_running_pipeline_jobs() == 1


def test_child_success_completes_parent_and_repeated_callbacks_are_idempotent():
    parent, child = handoff()
    finish_child(child)
    assert db.get_job(parent)["status"] == "completed"
    assert all(s == "completed" for s in states(parent).values())
    timestamp = db.get_job(parent)["completed_at"]
    db.update_job_status(child, "completed")
    assert db.get_job(parent)["completed_at"] == timestamp


def test_partial_failure_preserves_completed_parent_stages():
    parent, child = handoff()
    db.update_job_status(child, "running")
    db.update_job_status(child, "completed")
    db.update_job_status(child, "failed", log="species failed")
    assert states(parent) == {"culling": "completed", "keywords": "completed", "bird_species": "failed"}
    row = db.get_job(parent)
    assert row["status"] == "failed"
    assert f"#{child}" in row["log"]


def test_cancelling_queued_child_cancels_waiting_parent():
    parent, child = handoff()
    assert db.request_cancel_job(child)["success"]
    assert db.get_job(parent)["status"] == "cancelled"
    assert states(parent) == {"culling": "completed", "keywords": "cancelled", "bird_species": "cancelled"}


def test_cancelling_waiting_parent_cancels_its_child():
    parent, child = handoff()
    assert db.request_cancel_job(parent)["success"]
    assert db.get_job(child)["status"] == "cancelled"
    assert db.get_job(parent)["status"] == "cancelled"
    assert db.get_queued_jobs_count() == 0


def test_repeated_handoff_reuses_child_and_cannot_dispatch_parent_stages():
    parent, child = handoff()
    again, _ = db.enqueue_delegated_followup(parent, "/delegation/test", ["keywords", "bird_species"])
    assert again == child
    assert db.get_queued_jobs_count() == 1
    with pytest.raises(ValueError, match="delegated"):
        db.set_job_phase_state(parent, "keywords", "completed")


def test_startup_preserves_waiting_parent_when_child_is_queued():
    parent, child = handoff()
    assert parent not in db.recover_running_jobs()
    db.reconcile_delegated_jobs()
    assert db.get_job(parent)["runner_state"] == "waiting_child"
    assert db.get_job(child)["status"] == "queued"


def test_inplace_child_restart_reopens_parent_and_preserves_completed_stages():
    parent, child = handoff()
    db.update_job_status(child, "running")
    db.update_job_status(child, "completed")
    db.update_job_status(child, "failed")
    assert db.restart_failed_job(child)["success"]
    assert db.get_job(parent)["status"] == "running"
    assert db.get_job(parent)["completed_at"] is None
    assert states(parent)["keywords"] == "completed"
    db.update_job_status(child, "running")
    db.update_job_status(child, "completed")
    assert db.get_job(parent)["status"] == "completed"


def test_live_child_interruption_is_recovered_and_parent_resume_targets_child():
    parent, child = handoff()
    db.update_job_status(child, "running")
    recovered = db.recover_running_jobs()
    assert child in recovered and parent not in recovered
    assert db.get_job(parent)["status"] == "interrupted"
    db.requeue_job(parent)
    db.resume_job_phases(parent)
    assert db.get_job(child)["status"] == "queued"
    assert db.get_job(parent)["runner_state"] == "waiting_child"
    assert states(parent)["culling"] == "completed"
    assert db.dequeue_next_job()["id"] == child


def test_waiting_parent_pause_and_resume_do_not_dispatch_parent():
    parent, child = handoff()
    db.update_job_status(parent, "paused")
    assert db.get_job(child)["status"] == "paused"
    assert db.get_job(parent)["status"] == "paused"
    assert db.dequeue_next_job() is None
    db.update_job_status(parent, "running")
    assert db.get_job(child)["status"] == "queued"
    assert db.dequeue_next_job()["id"] == child


def test_running_child_cancellation_stops_only_its_owned_runner(monkeypatch):
    from modules.api import state

    parent, child = handoff()
    db.update_job_status(child, "running")
    runner = Mock(is_running=True, _dispatch_job_id=child)
    unrelated = Mock(is_running=True, _dispatch_job_id=99999)
    monkeypatch.setattr(state, "_tagging_runner", runner)
    monkeypatch.setattr(state, "_scoring_runner", unrelated)
    db.update_job_status(parent, "cancelled")
    runner.stop.assert_called_once()
    unrelated.stop.assert_not_called()
    assert db.get_job(child)["status"] == "cancelled"


def test_unrelated_same_type_runner_is_not_stopped(monkeypatch):
    from modules.api import state

    parent, child = handoff()
    db.update_job_status(child, "running")
    unrelated = Mock(is_running=True, _dispatch_job_id=99999)
    monkeypatch.setattr(state, "_tagging_runner", unrelated)
    db.update_job_status(parent, "cancelled")
    unrelated.stop.assert_not_called()


def test_cancellation_of_child_second_stage_stops_its_current_runner(monkeypatch):
    from modules.api import state

    parent, child = handoff()
    db.update_job_status(child, "running")
    db.update_job_status(child, "completed")
    tagging = Mock(is_running=False, _dispatch_job_id=child)
    birds = Mock(is_running=True, _dispatch_job_id=child)
    monkeypatch.setattr(state, "_tagging_runner", tagging)
    monkeypatch.setattr(state, "_bird_species_runner", birds)
    db.update_job_status(parent, "cancelled")
    birds.stop.assert_called_once()
    tagging.stop.assert_not_called()


def test_concurrent_handoffs_create_only_one_child():
    parent = db.create_job("/delegation/concurrent", phase_code="culling", job_type="selection", status="running")
    db.create_job_phases(parent, ["culling", "keywords"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: db.enqueue_delegated_followup(parent, "/delegation/concurrent", ["keywords"]), range(2)))
    assert results[0][0] == results[1][0]
    assert db.get_queued_jobs_count() == 1


def test_atomic_handoff_rolls_back_child_and_links_on_phase_write_failure(monkeypatch):
    parent = db.create_job("/delegation/rollback", phase_code="culling", job_type="selection", status="running")
    db.create_job_phases(parent, ["culling", "keywords", "bird_species"])
    original = db.enqueue_job_with_phases

    class FailingTransaction:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __getattr__(self, key):
            return getattr(self.wrapped, key)

        def execute(self, sql, params):
            if "INSERT INTO job_phases" in sql and params[2] == "bird_species":
                raise RuntimeError("phase insertion failed")
            return self.wrapped.execute(sql, params)

    def fail(*args, **kwargs):
        kwargs["tx"] = FailingTransaction(kwargs["tx"])
        return original(*args, **kwargs)

    monkeypatch.setattr(db, "enqueue_job_with_phases", fail)
    with pytest.raises(RuntimeError, match="phase insertion failed"):
        db.enqueue_delegated_followup(parent, "/delegation/rollback", ["keywords", "bird_species"])
    assert db.get_queued_jobs_count() == 0
    assert states(parent) == {"culling": "running", "keywords": "pending", "bird_species": "pending"}
    assert all(p["delegated_job_id"] is None for p in db.get_job_phases(parent))


def test_reconciliation_repairs_missed_parent_projection_without_new_work():
    parent, child = handoff()
    finish_child(child)
    conn = db.get_connector()
    conn.execute("UPDATE jobs SET status = 'running', runner_state = 'waiting_child', completed_at = NULL WHERE id = ?", (parent,))
    conn.execute("UPDATE job_phases SET state = 'pending', completed_at = NULL WHERE job_id = ? AND delegated_job_id = ?", (parent, child))
    assert parent in db.reconcile_delegated_jobs()
    assert db.get_job(parent)["status"] == "completed"
    assert db.get_queued_jobs_count() == 0


def test_duplicate_completion_emits_no_second_parent_terminal_event(monkeypatch):
    parent, child = handoff()
    broadcast = Mock()
    monkeypatch.setattr(db.event_manager, "broadcast_threadsafe", broadcast)
    finish_child(child)
    db.update_job_status(child, "completed")
    events = [c for c in broadcast.call_args_list if c.args[0] == "job_completed" and c.args[1]["job_id"] == parent]
    assert len(events) == 1


def test_fresh_child_retry_has_no_active_link_to_old_failed_parent():
    from modules.api.routers.electron_run_helpers import create_retry_job

    parent, child = handoff()
    db.update_job_status(child, "running")
    db.update_job_status(child, "failed")
    retry, _ = create_retry_job(db.get_job(child), "retry")
    assert db.get_job(retry)["parent_job_id"] is None
    finish_child(retry)
    assert db.get_job(parent)["status"] == "failed"


def test_delegated_parent_stages_are_not_phantom_running_work():
    parent, child = handoff()
    db.update_job_status(child, "running")
    candidates = db.list_phantom_running_job_phases(grace_seconds=0)
    assert all(row["job_id"] != parent for row in candidates)


def test_migration_is_idempotent_and_rejects_downgrade_with_unfinished_chain(monkeypatch):
    migration = importlib.import_module("migrations.versions.0040_delegated_jobs")
    historical = db.create_job("/delegation/historical", phase_code="keywords", status="completed", queue_payload={"parent_job_id": 98765})
    parent, child = handoff()

    def run(function):
        def operation(tx):
            monkeypatch.setattr(migration.op, "execute", tx.execute)
            function()
        return db.get_connector().run_transaction(operation)

    run(migration.upgrade)
    run(migration.upgrade)
    assert db.get_job(historical)["parent_job_id"] is None
    assert db.get_job(historical)["status"] == "completed"
    with pytest.raises(Exception, match="Drain unfinished"):
        run(migration.downgrade)
    assert db.get_job(child)["parent_job_id"] == parent
    finish_child(child)
    run(migration.downgrade)
    run(migration.upgrade)
    assert db.get_job(parent)["status"] == "completed"


def test_leaf_requeue_reopens_parent_in_the_same_transaction():
    parent, child = handoff()
    db.update_job_status(child, "running")
    db.update_job_status(child, "interrupted")
    db.requeue_job(child)
    assert db.get_job(parent)["status"] == "running"
    assert db.get_job(parent)["completed_at"] is None
    assert states(parent)["keywords"] == "queued"


def test_force_stage_reset_cannot_detach_delegated_work():
    parent, child = handoff()
    with pytest.raises(ValueError, match="delegated"):
        db.force_reset_job_phase_to_queued(parent, "culling")
    assert db.get_job(parent)["runner_state"] == "waiting_child"
    assert db.get_job(child)["status"] == "queued"


def test_nested_chain_projects_success_and_cancellation_to_all_ancestors():
    root = db.create_job("/delegation/nested", phase_code="culling", job_type="selection", status="running")
    db.create_job_phases(root, ["culling", "keywords", "bird_species"])
    middle, _ = db.enqueue_delegated_followup(root, "/delegation/nested", ["keywords", "bird_species"])
    db.update_job_status(middle, "running")
    db.update_job_status(middle, "completed")
    leaf, _ = db.enqueue_delegated_followup(middle, "/delegation/nested", ["bird_species"])
    assert db.get_job(root)["runner_state"] == "waiting_child"
    assert states(root)["keywords"] == "completed"
    db.request_cancel_job(root)
    assert all(db.get_job(jid)["status"] == "cancelled" for jid in (root, middle, leaf))
    assert states(root)["keywords"] == "completed"


def test_concurrent_child_completion_and_parent_cancel_leave_consistent_chain():
    parent, child = handoff()
    db.update_job_status(child, "running")
    db.update_job_status(child, "completed")
    barrier = threading.Barrier(2)

    def complete():
        barrier.wait()
        try:
            db.update_job_status(child, "completed")
        except ValueError as exc:
            assert "cancelled -> completed" in str(exc)

    def cancel():
        barrier.wait()
        db.request_cancel_job(parent)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(complete), pool.submit(cancel)]
        for future in futures:
            future.result(timeout=10)
    assert db.get_job(parent)["status"] == db.get_job(child)["status"]
    assert db.get_job(parent)["status"] in ("completed", "cancelled")
    assert states(parent)["keywords"] == "completed"


def test_dispatcher_with_capacity_one_runs_child_and_its_second_phase(monkeypatch):
    from modules.job_dispatcher import JobDispatcher
    from tests.support.fake_runners import FakePhaseRunner

    parent, child = handoff()
    started = []

    def on_start(path, job_id, **kwargs):
        started.append(job_id)
        db.update_job_status(job_id, "running")

    tagging = FakePhaseRunner(delay_s=0.03, on_start=on_start)
    birds = FakePhaseRunner(delay_s=0.03, on_start=on_start)
    monkeypatch.setattr(JobDispatcher, "_max_in_flight_jobs", staticmethod(lambda: 1))
    monkeypatch.setattr(JobDispatcher, "_jit_replan_phase", lambda self, job_id, payload, queue_key, input_path: (payload, [1], False))
    dispatcher = JobDispatcher(tagging_runner=tagging, bird_species_runner=birds)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and db.get_job(parent)["status"] != "completed":
        dispatcher.tick_for_tests()
        time.sleep(0.02)
    for runner in (tagging, birds):
        if runner._thread:
            runner._thread.join(timeout=1)
    assert started == [child, child]
    assert db.get_job(parent)["status"] == "completed"
    assert all(value == "completed" for value in states(parent).values())


def test_child_stage_projection_uses_actual_timestamps_without_parent_auto_advance():
    parent, child = handoff()
    db.update_job_status(child, "running")
    db.set_job_phase_state(child, "keywords", "completed")
    parent_rows = {p["phase_code"]: p for p in db.get_job_phases(parent)}
    child_rows = {p["phase_code"]: p for p in db.get_job_phases(child)}
    assert parent_rows["keywords"]["completed_at"] == child_rows["keywords"]["completed_at"]
    assert parent_rows["bird_species"]["started_at"] == child_rows["bird_species"]["started_at"]
    assert db.get_job(parent)["status"] == "running"
    db.update_job_status(child, "failed")
    assert states(parent)["keywords"] == "completed"


def test_notification_failure_after_commit_does_not_fail_successful_handoff(monkeypatch):
    parent = db.create_job("/delegation/audit", phase_code="culling", job_type="selection", status="running")
    db.create_job_phases(parent, ["culling", "keywords"])
    monkeypatch.setattr(db.audit, "record_audit", Mock(side_effect=RuntimeError("audit unavailable")))
    child, _ = db.enqueue_delegated_followup(parent, "/delegation/audit", ["keywords"])
    assert db.get_job(child)["parent_job_id"] == parent
    assert db.get_job(parent)["runner_state"] == "waiting_child"


def test_post_run_audit_failure_propagates_without_a_stale_parent_success_event(monkeypatch):
    parent, child = handoff()
    original = db._job_lifecycle_services

    def services():
        from dataclasses import replace

        return replace(original(), post_completion_audit=lambda jid: db._maybe_fail_job_on_post_audit_issues(jid, {"status": "issues_remaining"}) if jid == child else None)

    monkeypatch.setattr(db, "_job_lifecycle_services", services)
    monkeypatch.setattr(db.config, "get_config_value", lambda key, default=None: key == "processing.post_run_audit_fail_job_on_issues")
    events = Mock()
    monkeypatch.setattr(db.event_manager, "broadcast_threadsafe", events)
    finish_child(child)
    assert db.get_job(child)["status"] == "failed"
    assert db.get_job(parent)["status"] == "failed"
    assert all(value == "completed" for value in states(parent).values())
    successes = [call for call in events.call_args_list if call.args[0] == "job_completed" and call.args[1]["job_id"] == parent]
    assert successes == []


def test_queue_pause_of_child_projects_to_waiting_parent():
    parent, child = handoff()
    assert db.pause_queue_job(child)["success"]
    assert db.get_job(parent)["status"] == "paused"
    assert db.get_job(child)["status"] == "paused"
    db.requeue_job(child)
    assert db.get_job(parent)["status"] == "running"


def test_notification_lookup_failure_does_not_invalidate_committed_handoff(monkeypatch):
    parent = db.create_job("/delegation/notification", phase_code="culling", job_type="selection", status="running")
    db.create_job_phases(parent, ["culling", "keywords"])
    monkeypatch.setattr(db, "get_job", Mock(side_effect=RuntimeError("notification lookup unavailable")))
    child, _ = db.enqueue_delegated_followup(parent, "/delegation/notification", ["keywords"])
    row = db.get_connector().query_one("SELECT parent_job_id FROM jobs WHERE id = ?", (child,))
    assert row["parent_job_id"] == parent


def test_parent_audit_failure_survives_duplicate_completion_and_reconciliation(monkeypatch):
    from dataclasses import replace

    parent, child = handoff()
    original = db._job_lifecycle_services
    audited = []

    def audit_parent(job_id):
        if job_id == parent:
            audited.append(job_id)
            db._maybe_fail_job_on_post_audit_issues(job_id, {"status": "issues_remaining"})

    monkeypatch.setattr(db, "_job_lifecycle_services", lambda: replace(original(), post_completion_audit=audit_parent))
    monkeypatch.setattr(db.config, "get_config_value", lambda key, default=None: key == "processing.post_run_audit_fail_job_on_issues")
    finish_child(child)
    assert db.get_job(parent)["status"] == "failed"
    assert db.get_job(child)["status"] == "completed"
    db.update_job_status(child, "completed")
    db.reconcile_delegated_jobs()
    assert db.get_job(parent)["status"] == "failed"
    assert audited == [parent]


def test_failed_parent_with_finished_child_cannot_be_requeued_as_executor():
    parent, child = handoff()
    finish_child(child)
    db.get_connector().execute("UPDATE jobs SET status = 'failed', runner_state = 'failed' WHERE id = ?", (parent,))
    assert db.restart_failed_job(parent)["success"] is False
    with pytest.raises(ValueError, match="completed"):
        db.requeue_job(parent)
    assert db.get_job(parent)["status"] == "failed"
    assert db.get_job(child)["status"] == "completed"
    assert db.get_queued_jobs_count() == 0


def test_new_child_completion_after_repair_reopens_failed_parent():
    parent, child = handoff()
    db.update_job_status(child, "running")
    db.update_job_status(child, "completed")
    db.update_job_status(child, "failed")
    # Existing lifecycle supports failed -> completed reconciliation after a
    # successful pass. A new outcome must propagate, unlike a duplicate callback.
    db.set_job_phase_state(child, "bird_species", "completed")
    db.update_job_status(child, "completed")
    assert db.get_job(child)["status"] == "completed"
    assert db.get_job(parent)["status"] == "completed"
