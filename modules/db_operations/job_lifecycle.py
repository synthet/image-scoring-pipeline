"""Job creation and lifecycle operations with runtime-injected facade services.

Database transactions, phase advancement, notifications, and terminal cleanup
are kept separate while public imports remain in modules.db.
"""

import datetime
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JobLifecycleServices:
    """Capture the facade's current collaborators for one public operation."""

    get_connector: Callable[[], Any]
    get_phase_id: Callable
    audit: Any
    record_pipeline_event: Callable
    event_manager: Any
    logger: logging.Logger
    allowed_transitions: dict[str, set[str]]
    terminal_states: set[str]
    verify_completion: Callable
    resolve_sync_phase: Callable
    set_phase_state: Callable
    get_phases: Callable
    get_next_running_phase: Callable
    reconcile_running_phases: Callable
    post_completion_audit: Callable
    stale_running_message: str


def create_job(
    input_path,
    phase_code=None,
    job_type=None,
    status="pending",
    current_phase=None,
    next_phase_index=None,
    runner_state=None,
    queue_payload=None,
    description=None,
    *,
    services: JobLifecycleServices,
):
    """
    Create a new job record.

    Args:
        input_path: Path being processed.
        phase_code: Optional phase code (e.g. 'scoring') — resolves to phase_id FK.
        job_type:   Optional legacy job type string (deprecated, use phase_code).
        status:     Initial status (default: pending).
        current_phase: Current orchestrator phase code.
        next_phase_index: Next phase index in orchestrator order.
        runner_state: High-level runner/orchestrator state.
        queue_payload: Optional queue metadata payload persisted as JSON.
        description: Optional human-readable reason/scope for troubleshooting (plain text).
    """
    phase_id = None
    if phase_code:
        phase_id = services.get_phase_id(phase_code)
        if job_type is None:
            job_type = phase_code  # backfill legacy column

    now = datetime.datetime.now()
    payload_json = json.dumps(queue_payload) if queue_payload is not None else None
    rows = services.get_connector().execute_returning(
        """INSERT INTO jobs (input_path, phase_id, job_type, status, created_at, current_phase, next_phase_index, runner_state, enqueued_at, queue_payload, cancel_requested, description)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?) RETURNING id""",
        (
            input_path,
            phase_id,
            job_type,
            status,
            now,
            current_phase,
            next_phase_index,
            runner_state,
            now,
            payload_json,
            description,
        ),
    )
    job_id = rows[0]["id"] if rows else None

    services.audit.record_audit(
        "jobs",
        job_id,
        "insert",
        services.audit.build_insert_patch(
            {
                "status": status,
                "input_path": input_path,
                "job_type": job_type,
                "phase_id": phase_id,
                "current_phase": current_phase,
                "runner_state": runner_state,
                "description": description,
            }
        ),
        run_id=job_id,
        phase_code=phase_code,
        source="db.create_job",
    )

    services.record_pipeline_event(
        "state-change",
        f"Job #{job_id} created ({status})",
        workflow_run=job_id,
        stage_run=phase_code or job_type or "pipeline",
        step_run="job:create",
        category="job",
        metadata={
            "status": status,
            "input_path": input_path,
            "job_type": job_type,
            "phase_code": phase_code,
            "description": description,
        },
        source="db.create_job",
    )
    return job_id


def get_job(job_id, *, services: JobLifecycleServices):
    row = services.get_connector().query_one(
        "SELECT * FROM jobs WHERE id = ?", (job_id,)
    )
    return dict(row) if row else None


def set_job_execution_cursor(
    job_id,
    current_phase=None,
    next_phase_index=None,
    runner_state=None,
    *,
    services: JobLifecycleServices,
):
    """Persist pipeline execution cursor fields on a job row."""
    services.get_connector().execute(
        "UPDATE jobs SET current_phase = ?, next_phase_index = ?, runner_state = ? WHERE id = ?",
        (current_phase, next_phase_index, runner_state, job_id),
    )

    services.record_pipeline_event(
        "state-change",
        f"Job #{job_id} cursor updated",
        workflow_run=job_id,
        stage_run=current_phase or "pipeline",
        step_run="job:cursor",
        category="phase-transition",
        metadata={
            "current_phase": current_phase,
            "next_phase_index": next_phase_index,
            "runner_state": runner_state,
        },
        source="db.set_job_execution_cursor",
    )


def update_job_progress(job_id, percent, *, services: JobLifecycleServices):
    """Broadcast percent-complete progress for long-running maintenance jobs (Runs UI WebSocket)."""
    try:
        p = max(0, min(100, int(percent)))
    except (TypeError, ValueError):
        p = 0
    try:
        services.event_manager.broadcast_threadsafe(
            "job_progress",
            {
                "job_id": job_id,
                "job_type": "maintenance",
                "phase_code": "maintenance",
                "current": p,
                "total": 100,
            },
        )
    except Exception:
        services.logger.debug(
            "update_job_progress: broadcast failed for job_id=%s", job_id, exc_info=True
        )


def update_job_log(job_id, log, *, services: JobLifecycleServices):
    """Update ``jobs.log`` only, preserving the current job status/state-machine invariants."""

    def _tx(tx):
        row = tx.query_one("SELECT id FROM jobs WHERE id = ?", (job_id,))
        if not row:
            raise ValueError(f"Job not found: {job_id}")
        tx.execute("UPDATE jobs SET log = ? WHERE id = ?", (log, job_id))

    services.get_connector().run_transaction(_tx)


def job_type_for_phase_dispatch(phase_code: str) -> str:
    """Map ``job_phases.phase_code`` to ``jobs.job_type`` for JobDispatcher routing.

    Reads ``modules.phases.PHASE_TO_JOB_TYPE`` rather than repeating it.  ``cluster`` /
    ``clustering`` are not phase codes -- they are the legacy ClusteringRunner job type,
    which the dispatcher accepts alongside ``selection`` -- so they pass through.
    """
    from modules.phases import PHASE_TO_JOB_TYPE

    pc = (phase_code or "").strip().lower()
    if pc in ("cluster", "clustering"):
        return pc
    return PHASE_TO_JOB_TYPE.get(pc, pc or "scoring")


def get_running_job_for_phase_continuation(*, services: JobLifecycleServices):
    """Return a job row plus active ``job_phases`` code for multi-phase continuation (dispatcher).

    Picks the oldest ``jobs.id`` with ``status='running'`` and a ``job_phases`` row in
    ``running`` (preferred) or ``queued`` (resumable after phantom reconciliation).
    """
    row = services.get_connector().query_one(
        """
        SELECT j.*, jp.phase_code AS _active_phase_code
        FROM jobs j
        INNER JOIN job_phases jp ON jp.job_id = j.id AND jp.state IN ('running', 'queued')
        WHERE j.status = 'running'
          AND j.job_type != 'ui_pipeline'
        ORDER BY
          CASE jp.state WHEN 'running' THEN 0 ELSE 1 END,
          j.id ASC,
          jp.phase_order ASC
        FETCH FIRST 1 ROWS ONLY
        """
    )
    return dict(row) if row else None


def _complete_multi_phase_job(
    tx,
    job_id,
    new_status,
    effect_log,
    runner_state,
    row,
    now,
    final_phase,
    final_next_idx,
    phase_state_map,
    services,
):
    old_status = (row["status"] or "pending").strip().lower()
    root_job_type = row.get("job_type")
    phase_state = phase_state_map.get(new_status, "running")
    multi = services.resolve_sync_phase(job_id, new_status, tx=tx)
    if multi:
        services.set_phase_state(
            job_id,
            multi,
            phase_state,
            error_message=effect_log
            if new_status in {"failed", "interrupted"}
            else None,
            tx=tx,
        )

    phases = services.get_phases(job_id, tx=tx)
    terminal_states = {"completed", "skipped", "canceled", "cancelled"}

    def _phase_terminal(p):
        return (p.get("state") or "").strip().lower() in terminal_states

    all_terminal = (not phases) or all(_phase_terminal(p) for p in phases)
    eff_log = effect_log if effect_log is not None else row.get("log")

    if not all_terminal:
        active = next(
            (p for p in phases if (p.get("state") or "").strip().lower() == "running"),
            None,
        )
        if active is None:
            active = next((p for p in phases if not _phase_terminal(p)), None)
        if active is None:
            pc_fallback = services.get_next_running_phase(job_id, tx=tx)
            if pc_fallback:
                po_fb = next(
                    (
                        int(p["phase_order"])
                        for p in phases
                        if (p.get("phase_code") or "") == pc_fallback
                    ),
                    0,
                )
                active = {"phase_code": pc_fallback, "phase_order": po_fb}
        if active:
            pc = active.get("phase_code")
            po = int(active.get("phase_order") or 0)
            pid = services.get_phase_id(pc)
            tx.execute(
                "UPDATE jobs SET status = 'running', finished_at = NULL, completed_at = NULL, "
                "log = ?, current_phase = ?, next_phase_index = ?, runner_state = 'running', "
                "phase_id = COALESCE(?, phase_id) WHERE id = ?",
                (eff_log, pc, po, pid, job_id),
            )
            return old_status, "running", pc, po, "running", root_job_type

    final_rs = runner_state if runner_state is not None else "completed"
    tx.execute(
        "UPDATE jobs SET status = ?, finished_at = ?, completed_at = ?, log = ?, current_phase = ?, next_phase_index = ?, runner_state = ? WHERE id = ?",
        ("completed", now, now, eff_log, final_phase, final_next_idx, final_rs, job_id),
    )
    return old_status, "completed", final_phase, final_next_idx, final_rs, root_job_type


def _sync_job_phase_status(
    tx, job_id, new_status, n_phases, effect_log, phase_state_map, services
):
    # Keep job_phases state in sync for phase-bound jobs
    try:
        skip_multi_completed = new_status == "completed" and n_phases > 1
        job_row = tx.query_one(
            "SELECT phase_id, job_type FROM jobs WHERE id = ?", (job_id,)
        )
        phase_code = None
        if job_row:
            if job_row["phase_id"]:
                p_row = tx.query_one(
                    "SELECT code FROM pipeline_phases WHERE id = ?",
                    (job_row["phase_id"],),
                )
                if p_row:
                    phase_code = p_row["code"]
            if not phase_code and job_row["job_type"] not in (
                "pipeline",
                "ui_pipeline",
            ):
                phase_code = job_row["job_type"]
            if not phase_code and job_row["job_type"] in ("pipeline", "ui_pipeline"):
                phase_code = services.get_next_running_phase(job_id, tx=tx)

        phase_state = phase_state_map.get(new_status, "running")

        if n_phases > 1 and not skip_multi_completed:
            multi = services.resolve_sync_phase(job_id, new_status, tx=tx)
            if multi:
                services.set_phase_state(
                    job_id,
                    multi,
                    phase_state,
                    error_message=effect_log
                    if new_status in {"failed", "interrupted"}
                    else None,
                    tx=tx,
                )
        elif phase_code and not (n_phases > 1):
            services.set_phase_state(
                job_id,
                phase_code,
                phase_state,
                error_message=effect_log
                if new_status in {"failed", "interrupted"}
                else None,
                tx=tx,
            )
    except Exception as e:
        services.logger.debug(
            "update_job_status: failed to sync job_phases for job %s: %s", job_id, e
        )


def _update_status_transaction(
    tx,
    job_id,
    effect_status,
    effect_log,
    current_phase,
    next_phase_index,
    runner_state,
    services,
):
    row = tx.query_one(
        "SELECT status, current_phase, next_phase_index, runner_state, log, phase_id, job_type FROM jobs WHERE id = ?",
        (job_id,),
    )
    if not row:
        raise ValueError(f"Job not found: {job_id}")

    old_status = (row["status"] or "pending").strip().lower()
    new_status = effect_status
    root_job_type = row.get("job_type")

    allowed_next = services.allowed_transitions.get(old_status)
    if (
        allowed_next is not None
        and old_status != new_status
        and new_status not in allowed_next
    ):
        raise ValueError(
            f"Invalid job status transition: {old_status} -> {new_status} (job_id={job_id})"
        )

    final_log = effect_log
    # Keep existing cursor values unless caller explicitly overrides
    final_phase = current_phase if current_phase is not None else row["current_phase"]
    final_next_idx = (
        next_phase_index if next_phase_index is not None else row["next_phase_index"]
    )
    final_runner_state = (
        runner_state if runner_state is not None else row["runner_state"]
    )

    now = datetime.datetime.now()
    count_row = tx.query_one(
        "SELECT COUNT(*) AS cnt FROM job_phases WHERE job_id = ?", (job_id,)
    )
    n_phases = int(count_row["cnt"]) if count_row else 0

    phase_state_map = {
        "queued": "queued",
        "running": "running",
        "paused": "paused",
        "cancel_requested": "cancel_requested",
        "restarting": "restarting",
        "completed": "completed",
        "failed": "failed",
        "canceled": "cancelled",
        "cancelled": "cancelled",
        "interrupted": "interrupted",
    }

    # Multi-phase: completing one stage must not mark the whole job terminal.
    if new_status == "completed" and n_phases > 1:
        return _complete_multi_phase_job(
            tx,
            job_id,
            new_status,
            effect_log,
            runner_state,
            row,
            now,
            final_phase,
            final_next_idx,
            phase_state_map,
            services,
        )

    if new_status == "running":
        tx.execute(
            "UPDATE jobs SET status = ?, started_at = COALESCE(started_at, ?), log = ?, current_phase = ?, next_phase_index = ?, runner_state = ? WHERE id = ?",
            (
                new_status,
                now,
                final_log,
                final_phase,
                final_next_idx,
                final_runner_state,
                job_id,
            ),
        )
    elif new_status in services.terminal_states:
        tx.execute(
            "UPDATE jobs SET status = ?, finished_at = ?, completed_at = ?, log = ?, current_phase = ?, next_phase_index = ?, runner_state = ? WHERE id = ?",
            (
                new_status,
                now,
                now,
                final_log,
                final_phase,
                final_next_idx,
                final_runner_state,
                job_id,
            ),
        )
    else:
        tx.execute(
            "UPDATE jobs SET status = ?, log = ?, current_phase = ?, next_phase_index = ?, runner_state = ? WHERE id = ?",
            (
                new_status,
                final_log,
                final_phase,
                final_next_idx,
                final_runner_state,
                job_id,
            ),
        )

    _sync_job_phase_status(
        tx, job_id, new_status, n_phases, effect_log, phase_state_map, services
    )

    return (
        old_status,
        new_status,
        final_phase,
        final_next_idx,
        final_runner_state,
        root_job_type,
    )


def _record_status_change(
    job_id,
    old_status,
    broadcast_status,
    final_phase,
    final_next_idx,
    final_runner_state,
    job_type_after,
    services,
):
    services.audit.record_audit(
        "jobs",
        job_id,
        "update",
        services.audit.build_field_update_patch("status", old_status, broadcast_status),
        run_id=job_id,
        phase_code=final_phase,
        source="db.update_job_status",
    )

    event_type = "state-change"
    severity = "info"
    if broadcast_status == "failed":
        event_type = "error"
        severity = "error"
    elif broadcast_status in ("completed", "canceled"):
        event_type = "recovery"
        severity = "warning" if broadcast_status == "canceled" else "info"

    services.record_pipeline_event(
        event_type,
        f"Job #{job_id} status: {old_status} → {broadcast_status}",
        workflow_run=job_id,
        stage_run=final_phase or "pipeline",
        step_run="job:status",
        category="job",
        severity=severity,
        metadata={
            "old_status": old_status,
            "status": broadcast_status,
            "current_phase": final_phase,
            "next_phase_index": final_next_idx,
            "runner_state": final_runner_state,
        },
        critical=broadcast_status in ("failed", "interrupted"),
        source="db.update_job_status",
    )

    # Broadcast job status update
    try:
        from modules.events import event_manager

        payload = {
            "job_id": job_id,
            "status": broadcast_status,
            "current_phase": final_phase,
            "next_phase_index": final_next_idx,
            "runner_state": final_runner_state,
        }
        if job_type_after:
            payload["job_type"] = job_type_after
        event_manager.broadcast_threadsafe(f"job_{broadcast_status}", payload)
    except Exception:
        pass


def _cleanup_terminal_job(job_id, broadcast_status, services):
    if broadcast_status in (
        "completed",
        "failed",
        "canceled",
        "cancelled",
        "interrupted",
    ):
        try:
            from modules.phase_work_claims import release_claims_for_job

            release_claims_for_job(int(job_id))
        except Exception:
            services.logger.debug(
                "update_job_status: release work claims failed for job %s",
                job_id,
                exc_info=True,
            )

    if broadcast_status in ("completed", "failed", "canceled", "cancelled"):
        try:
            n_ips = services.reconcile_running_phases(
                [job_id],
                error_message=f"{services.stale_running_message}:job_{broadcast_status}",
                in_flight_to="failed",
            )
            if n_ips:
                services.logger.info(
                    "update_job_status: reconciled %s stale image_phase_status rows for job %s",
                    n_ips,
                    job_id,
                )
        except Exception:
            services.logger.exception(
                "update_job_status: image_phase_status reconcile failed for job %s",
                job_id,
            )
    elif broadcast_status == "interrupted":
        try:
            n_ips = services.reconcile_running_phases(
                [job_id],
                error_message=f"{services.stale_running_message}:job_{broadcast_status}",
                in_flight_to="not_started",
            )
            if n_ips:
                services.logger.info(
                    "update_job_status: reconciled %s resumable image_phase_status rows for job %s",
                    n_ips,
                    job_id,
                )
        except Exception:
            services.logger.exception(
                "update_job_status: image_phase_status reconcile failed for job %s",
                job_id,
            )

    if broadcast_status == "completed":
        try:
            services.post_completion_audit(int(job_id))
        except Exception:
            services.logger.exception(
                "update_job_status: post-run data quality audit failed for job %s",
                job_id,
            )


def update_job_status(
    job_id,
    status,
    log=None,
    current_phase=None,
    next_phase_index=None,
    runner_state=None,
    *,
    services: JobLifecycleServices,
):
    # Normalize spelling for writes
    effect_status = (status or "").strip().lower()
    if effect_status == "canceled":
        effect_status = "cancelled"

    effect_log = log
    if effect_status == "completed":
        strict_fail = services.verify_completion(job_id)
        if strict_fail:
            effect_status = "failed"
            effect_log = strict_fail if log is None else f"{log}\n{strict_fail}"

    def _tx(tx):
        return _update_status_transaction(
            tx,
            job_id,
            effect_status,
            effect_log,
            current_phase,
            next_phase_index,
            runner_state,
            services,
        )

    result = services.get_connector().run_transaction(_tx)
    _record_status_change(job_id, *result, services)
    _cleanup_terminal_job(job_id, result[1], services)
