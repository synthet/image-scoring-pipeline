"""Transactional lifecycle for culling's delegated phase plans.

Links are database facts; payload parent IDs remain audit metadata only. Waiting
parents occupy no executor slot, and their stages are projections of child work.
"""

import datetime
import threading


WAITING_CHILD = "waiting_child"
SUCCESS = {"completed", "skipped"}
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def lock_chain(tx, job_id):
    """Lock ancestors before descendants (links always point to older job IDs)."""
    ids = []
    current = job_id
    while current is not None:
        if current in ids:
            raise ValueError("Invalid delegated job cycle")
        ids.append(current)
        row = tx.query_one("SELECT parent_job_id FROM jobs WHERE id = ?", (current,))
        current = (row or {}).get("parent_job_id")
    for jid in reversed(ids):
        tx.query_one("SELECT id FROM jobs WHERE id = ? FOR UPDATE", (jid,))


def child_for_parent(tx, job_id):
    row = tx.query_one(
        "SELECT delegated_job_id FROM job_phases WHERE job_id = ? "
        "AND delegated_job_id IS NOT NULL ORDER BY phase_order FETCH FIRST 1 ROWS ONLY",
        (job_id,),
    )
    return (row or {}).get("delegated_job_id")


def publish(changes):
    """Publish durable transitions after commit, using the existing audit/cleanup."""
    from modules import db
    from modules.db_operations.job_lifecycle import _cleanup_terminal_job, _record_status_change

    services = db._job_lifecycle_services()
    for job_id, result in changes:
        try:
            current = db.get_job(job_id)
        except Exception:
            services.logger.exception("Delegated job #%s notification lookup failed after commit", job_id)
            continue
        if not current or current["status"] != result[1]:
            continue  # A post-run audit or concurrent control superseded this transition.
        try:
            _record_status_change(job_id, *result, services)
        except Exception:
            services.logger.exception("Delegated job #%s notification failed after commit", job_id)
        if result[0] != result[1]:
            _cleanup_terminal_job(job_id, result[1], services)


def propagate(tx, child_id, *, new_completion=False):
    """Project one child's committed states through its ancestors. Locks held by caller."""
    changes = []
    while True:
        child = tx.query_one("SELECT * FROM jobs WHERE id = ?", (child_id,))
        parent_id = (child or {}).get("parent_job_id")
        if parent_id is None:
            break
        parent = tx.query_one("SELECT * FROM jobs WHERE id = ?", (parent_id,))
        if not parent:
            raise ValueError(f"Missing delegated parent #{parent_id}")
        # Cancellation wins a completion race. Explicit retry never reopens cancelled work.
        child_status = (child.get("status") or "").replace("canceled", "cancelled")
        if parent["status"] in ("cancelled", "canceled"):
            break
        if parent["status"] == "completed" and child_status != "failed":
            break
        if parent["status"] == "failed" and child_status == "completed" and not new_completion:
            # A finished child cannot clear the parent's own audit failure. An
            # in-place retry reopens it, or a genuinely new repair outcome does.
            break
        phases = tx.query(
            "SELECT p.id, p.phase_code, p.state, p.started_at, p.completed_at, p.error_message, "
            "c.state AS child_state, c.started_at AS child_started, c.completed_at AS child_completed, "
            "c.error_message AS child_error FROM job_phases p "
            "LEFT JOIN job_phases c ON c.job_id = p.delegated_job_id AND c.phase_code = p.phase_code "
            "WHERE p.job_id = ? AND p.delegated_job_id = ? ORDER BY p.phase_order",
            (parent_id, child_id),
        )
        now = datetime.datetime.now()
        phase_changed = False
        for phase in phases:
            state = phase.get("child_state") or "pending"
            if child_status in TERMINAL - {"completed"} and state not in SUCCESS:
                state = child_status
            if child_status == "completed" and state not in SUCCESS:
                raise ValueError(f"Delegated job #{child_id} completed with unfinished stages")
            started = phase.get("child_started")
            completed = phase.get("child_completed") if state in SUCCESS else None
            if state in TERMINAL - {"completed"}:
                completed = phase.get("child_completed") or phase.get("completed_at") or now
            message = phase.get("child_error")
            if state in ("failed", "cancelled", "interrupted"):
                message = f"Delegated job #{child_id}: {child.get('log') or state}"
            elif state not in SUCCESS:
                message = f"delegated to job #{child_id}"
            values = (state, started, completed, message)
            before = tuple(phase.get(k) for k in ("state", "started_at", "completed_at", "error_message"))
            if values != before:
                tx.execute(
                    "UPDATE job_phases SET state = ?, started_at = ?, completed_at = ?, error_message = ? WHERE id = ?",
                    (*values, phase["id"]),
                )
                phase_changed = True
        if not phases:
            break  # An independent retry keeps ancestry in audit metadata, not active links.
        status = child_status if child_status in TERMINAL else (
            "paused" if child_status in ("paused", "user_pause") else "running"
        )
        runner_state = status if status in TERMINAL else WAITING_CHILD
        old_status = parent["status"]
        message = parent.get("log")
        if status in ("failed", "cancelled", "interrupted"):
            message = f"Delegated job #{child_id}: {child.get('log') or status}"
        elif old_status in TERMINAL:
            message = f"Delegated job #{child_id}: {child_status}"
        current = next((p["phase_code"] for p in phases if p.get("child_state") not in SUCCESS), phases[-1]["phase_code"])
        if phase_changed or old_status != status or parent.get("runner_state") != runner_state:
            done_at = (parent.get("completed_at") or now) if status in TERMINAL else None
            tx.execute(
                "UPDATE jobs SET status = ?, runner_state = ?, current_phase = ?, log = ?, "
                "finished_at = ?, completed_at = ?, queue_position = NULL WHERE id = ?",
                (status, runner_state, current, message, done_at, done_at, parent_id),
            )
            changes.append((parent_id, (old_status, status, current, parent.get("next_phase_index"), runner_state, parent.get("job_type"))))
        child_id = parent_id
    return changes


def enqueue(parent_id, input_path, phase_codes, queue_payload=None, description=None):
    from modules import db
    from modules.phases import job_type_for_phase

    codes = list(dict.fromkeys(phase_codes))
    if not codes:
        raise ValueError("Delegated phase plan must not be empty")
    payload = dict(queue_payload or {})
    payload["parent_job_id"] = parent_id
    changes = []

    def operation(tx):
        lock_chain(tx, parent_id)
        parent = tx.query_one("SELECT * FROM jobs WHERE id = ?", (parent_id,))
        if not parent:
            raise ValueError("Delegation requires a running parent")
        existing = child_for_parent(tx, parent_id)
        if existing is not None:
            return existing, 0
        if parent["status"] != "running":
            raise ValueError("Delegation requires a running parent")
        phases = tx.query("SELECT phase_code, state FROM job_phases WHERE job_id = ?", (parent_id,))
        remaining = {p["phase_code"] for p in phases if p["phase_code"] != "culling" and p["state"] not in SUCCESS}
        if remaining != set(codes):
            raise ValueError("Delegated phase plan does not match unfinished parent stages")
        child_id, position = db.enqueue_job_with_phases(
            input_path, phase_code=codes[0], job_type=job_type_for_phase(codes[0]),
            queue_payload=payload, description=description, phase_codes=codes, tx=tx,
        )
        tx.execute("UPDATE jobs SET parent_job_id = ? WHERE id = ?", (parent_id, child_id))
        now = datetime.datetime.now()
        tx.execute(
            "UPDATE job_phases SET state = 'completed', completed_at = ?, "
            "started_at = COALESCE(started_at, ?) WHERE job_id = ? AND phase_code = 'culling'",
            (now, now, parent_id),
        )
        for code in codes:
            tx.execute(
                "UPDATE job_phases SET delegated_job_id = ?, state = 'pending', started_at = NULL, "
                "completed_at = NULL, error_message = ? WHERE job_id = ? AND phase_code = ?",
                (child_id, f"delegated to job #{child_id}", parent_id, code),
            )
        changes.extend(propagate(tx, child_id))
        return child_id, position

    result = db.get_connector().run_transaction(operation)
    publish(changes)
    return result


def reconcile():
    """Repair missed projections after a crash without scheduling another child."""
    from modules import db

    rows = db.get_connector().query(
        "SELECT DISTINCT j.id FROM jobs j JOIN job_phases p ON p.delegated_job_id = j.id "
        "JOIN jobs parent ON parent.id = p.job_id "
        "WHERE parent.status NOT IN ('completed', 'cancelled', 'canceled') "
        "OR (parent.status = 'completed' AND j.status = 'failed') ORDER BY j.id DESC"
    )
    changes = []
    for row in rows:
        def operation(tx):
            lock_chain(tx, row["id"])
            return propagate(tx, row["id"])
        changes.extend(db.get_connector().run_transaction(operation))
    publish(changes)
    return [job_id for job_id, _ in changes]


def control(parent_id, status, log=None):
    """Control only linked work. Return None for an ordinary job."""
    from modules import db

    changes = []
    stopped = []

    def operation(tx):
        lock_chain(tx, parent_id)
        child_id = child_for_parent(tx, parent_id)
        if child_id is None:
            return None
        parent = tx.query_one("SELECT status FROM jobs WHERE id = ?", (parent_id,))
        if parent["status"] in ("completed", "cancelled", "canceled"):
            return {"success": False, "reason": "already_finished", "status": parent["status"]}
        if status not in ("cancelled", "paused", "running"):
            raise ValueError("Invalid control of delegated work; use child resume or a fresh retry")
        chain = [parent_id]
        while child_id is not None:
            tx.query_one("SELECT id FROM jobs WHERE id = ? FOR UPDATE", (child_id,))
            chain.append(child_id)
            child_id = child_for_parent(tx, child_id)
        leaf = tx.query_one("SELECT * FROM jobs WHERE id = ?", (chain[-1],))
        if leaf["status"] in ("completed", "cancelled", "canceled"):
            changes.extend(propagate(tx, leaf["id"]))
            return {"success": False, "reason": "child_finished", "status": leaf["status"], "child_job_id": leaf["id"]}
        if status == "running":
            # Resuming an interrupted/paused chain queues the leaf, never the parent.
            if leaf["status"] in ("paused", "interrupted", "failed"):
                db.requeue_job(leaf["id"], tx=tx)
                db.resume_job_phases(leaf["id"], tx=tx)
                if leaf["status"] == "failed":
                    tx.execute("UPDATE jobs SET retry_count = COALESCE(retry_count, 0) + 1 WHERE id = ?", (leaf["id"],))
        else:
            if leaf["status"] == "running":
                stopped.append(dict(leaf))
            old = leaf["status"]
            now = datetime.datetime.now()
            terminal_at = now if status == "cancelled" else None
            tx.execute(
                "UPDATE jobs SET status = ?, runner_state = ?, cancel_requested = ?, queue_position = NULL, "
                "finished_at = ?, completed_at = ?, log = ? WHERE id = ?",
                (status, status, int(status == "cancelled"), terminal_at, terminal_at, log, leaf["id"]),
            )
            tx.execute(
                "UPDATE job_phases SET state = ?, completed_at = ?, error_message = ? "
                "WHERE job_id = ? AND state NOT IN ('completed', 'skipped')",
                (status, terminal_at, log, leaf["id"]),
            )
            changes.append((leaf["id"], (old, status, leaf.get("current_phase"), leaf.get("next_phase_index"), status, leaf.get("job_type"))))
        changes.extend(propagate(tx, leaf["id"]))
        return {"success": True, "status": status}

    result = db.get_connector().run_transaction(operation)
    publish(changes)
    for row in stopped:
        stop_owned_runner(row)
        if status == "paused":
            db.reconcile_stale_running_phases_for_jobs(
                [row["id"]], error_message=db.GRACEFUL_PAUSE_MSG, in_flight_to="not_started",
            )
    return result


def stop_owned_runner(job):
    """A waiting parent must never stop an unrelated runner of the same type."""
    from modules.api import state

    phase = (job.get("current_phase") or "").strip().lower() or state._map_job_row_to_dispatch_phase(job)
    names = {
        "culling": "selection", "keywords": "tagging", "clustering": "clustering",
    }
    runner = getattr(state, f"_{names.get(phase, phase)}_runner", None)
    if runner is not None and getattr(runner, "_dispatch_job_id", None) == job["id"] and runner.is_running:
        runner.stop()
        thread = getattr(runner, "_thread", None)
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=4.0)
