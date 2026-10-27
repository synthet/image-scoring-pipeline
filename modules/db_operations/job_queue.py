"""Job queue lookup, scheduling, display, and user controls.

Callers supply the current facade collaborators so database test seams and
public imports remain compatible during the legacy module decomposition.
"""

import datetime
import json
from collections.abc import Callable
from typing import Any


def find_active_job_for_folder(
    input_path,
    job_type=None,
    *,
    get_connector: Callable[[], Any],
    active_statuses: tuple[str, ...],
):
    """Return the id of an existing active job targeting the same logical folder.

    "Same logical folder" means the canonicalized (WSL) form matches: a Windows
    submission ``D:\\Photos\\Z8\\2026-05-09`` and a WSL submission
    ``/mnt/d/Photos/Z8/2026-05-09`` collapse to the same key. This is the
    duplicate-job hazard the audit on 2026-05-09 surfaced (jobs 2351 vs 2352).

    "Active" means ``status IN (queued, running, paused, user_pause, restarting)``.
    Terminal jobs (completed/failed/cancelled/interrupted/skipped) are ignored —
    re-running a folder after a terminal job is a legitimate operation.

    Args:
        input_path: Path the new submission would use (Windows or WSL form).
        job_type: Optional ``jobs.job_type`` filter (e.g. ``"indexing"``,
            ``"scoring"``). When ``None`` matches any type.

    Returns:
        Existing job id (int) or ``None`` if no active duplicate exists.
    """
    from modules import utils

    if not input_path:
        return None

    canonical = (
        utils.convert_path_to_wsl(input_path)
        if hasattr(utils, "convert_path_to_wsl")
        else input_path
    )
    canonical = canonical or input_path

    placeholders = ",".join(["?"] * len(active_statuses))
    sql = f"SELECT id, input_path FROM jobs WHERE status IN ({placeholders})"
    params: list = list(active_statuses)
    if job_type:
        sql += " AND job_type = ?"
        params.append(job_type)

    rows = get_connector().query(sql, tuple(params)) or []
    for r in rows:
        existing_path = r.get("input_path") if isinstance(r, dict) else None
        if not existing_path:
            continue
        existing_canonical = (
            utils.convert_path_to_wsl(existing_path)
            if hasattr(utils, "convert_path_to_wsl")
            else existing_path
        )
        existing_canonical = existing_canonical or existing_path
        if existing_canonical == canonical:
            return int(r["id"])
    return None


def enqueue_job(
    input_path,
    phase_code=None,
    job_type=None,
    queue_payload=None,
    description=None,
    *,
    get_connector: Callable[[], Any],
    get_phase_id: Callable,
):
    """Create a queued job with a stable internal sort key and dense display position."""
    phase_id = get_phase_id(phase_code) if phase_code else None
    if job_type is None:
        job_type = phase_code

    now = datetime.datetime.now()
    payload_dict = {}
    if queue_payload is None:
        payload_json = None
    elif isinstance(queue_payload, dict):
        payload_dict = queue_payload
        payload_json = json.dumps(queue_payload)
    elif isinstance(queue_payload, str):
        # Callers (e.g. maintenance API) sometimes pass an already-serialized JSON string.
        payload_json = queue_payload
        try:
            parsed = json.loads(queue_payload)
            if isinstance(parsed, dict):
                payload_dict = parsed
        except Exception:
            payload_dict = {}
    else:
        payload_json = json.dumps(queue_payload)

    from modules.job_priority import resolve_job_enqueue_priority

    priority = resolve_job_enqueue_priority(payload_dict, job_type=job_type)
    target_scope = None
    if payload_dict:
        target_scope = payload_dict.get("target_scope") or payload_dict.get("scope")
    if not target_scope:
        target_scope = input_path

    def _tx(tx):
        rows = tx.execute_returning(
            """
            INSERT INTO jobs (
                input_path, phase_id, job_type, status, queue_position,
                created_at, enqueued_at, queue_payload, cancel_requested,
                priority, target_scope, retry_count, description
            ) VALUES (?, ?, ?, 'queued', NULL, ?, ?, ?, 0, ?, ?, 0, ?) RETURNING id
            """,
            (
                input_path,
                phase_id,
                job_type,
                now,
                now,
                payload_json,
                priority,
                target_scope,
                description,
            ),
        )
        job_id = rows[0]["id"] if rows else None
        if not job_id:
            raise RuntimeError("Failed to insert job row")

        # Persist a stable queue ordering key using the DB identity.
        tx.execute("UPDATE jobs SET queue_position = ? WHERE id = ?", (job_id, job_id))

        # Return dense user-facing queue position (1..N), not the internal sort key.
        count_rows = tx.query(
            """
            SELECT COUNT(*) AS cnt FROM jobs
            WHERE status = 'queued' AND COALESCE(queue_position, id) <= ?
            """,
            (job_id,),
        )
        display_position = int((count_rows[0].get("cnt") or 0) if count_rows else 0)
        return job_id, display_position

    try:
        return get_connector().run_transaction(_tx)
    except RuntimeError:
        return None, 0


def count_running_pipeline_jobs(
    *, exclude_maintenance: bool = True, get_connector: Callable[[], Any]
) -> int:
    """Count jobs with status=running (optionally excluding maintenance)."""
    try:
        sql = "SELECT COUNT(*) AS cnt FROM jobs WHERE status = 'running' AND COALESCE(runner_state, '') != 'waiting_child'"
        if exclude_maintenance:
            sql += " AND COALESCE(job_type, '') != 'maintenance'"
        row = get_connector().query_one(sql)
        if not row:
            return 0
        return int(row.get("cnt") or 0)
    except Exception:
        return 0


def adjust_job_priority(job_id, delta, *, get_connector: Callable[[], Any]):
    """Increase/decrease job priority for queued/paused jobs."""
    try:
        d = int(delta)
    except Exception:
        d = 10

    def _tx(tx):
        rowcount = tx.execute(
            """
            UPDATE jobs
            SET priority = CASE
                WHEN COALESCE(priority, 100) + ? < 1 THEN 1
                WHEN COALESCE(priority, 100) + ? > 999 THEN 999
                ELSE COALESCE(priority, 100) + ?
            END
            WHERE id = ? AND status IN ('queued', 'paused')
            """,
            (d, d, d, job_id),
        )
        if rowcount > 0:
            row = tx.query_one("SELECT priority FROM jobs WHERE id = ?", (job_id,))
            new_priority = (
                int(row["priority"]) if row and row["priority"] is not None else 100
            )
        else:
            new_priority = None
        return {"success": rowcount > 0, "priority": new_priority}

    return get_connector().run_transaction(_tx)


def requeue_job(
    job_id,
    *,
    get_connector: Callable[[], Any],
    allowed_transitions: dict[str, set[str]],
    tx=None,
    resume_job_phases=None,
):
    """Reset an existing job row to queued status (in-place resume).

    Resets started_at, finished_at, completed_at and bumps enqueued_at.
    Updates queue_position so it sorts after any already-queued jobs.
    Returns (job_id, display_position).
    """
    now = datetime.datetime.now()
    from modules.db_operations import job_delegation

    changes = []
    owns_transaction = tx is None

    def _tx(tx):
        job_delegation.lock_chain(tx, job_id)
        row = tx.query_one("SELECT status, parent_job_id FROM jobs WHERE id = ?", (job_id,))
        if not row:
            raise ValueError(f"Job {job_id} not found")
        old_status = (row["status"] or "").strip().lower()
        allowed = allowed_transitions.get(old_status, set())
        if "queued" not in allowed:
            raise ValueError(f"Cannot requeue job from status '{old_status}'")

        tx.execute(
            """
            UPDATE jobs
            SET status = 'queued',
                started_at = NULL,
                finished_at = NULL,
                completed_at = NULL,
                enqueued_at = ?,
                queue_position = ?,
                runner_state = NULL,
                current_phase = NULL,
                cancel_requested = 0
            WHERE id = ?
            """,
            (now, job_id, job_id),
        )

        pos_row = tx.query_one(
            "SELECT COUNT(*) FROM jobs WHERE status = 'queued' AND COALESCE(queue_position, id) <= ?",
            (job_id,),
        )
        display_position = int(
            (pos_row.get("count") or pos_row.get("COUNT(*)") or 0) if pos_row else 0
        )
        if row.get("parent_job_id") is not None and resume_job_phases is not None:
            resume_job_phases(job_id, tx=tx)
            if owns_transaction:
                changes.extend(job_delegation.propagate(tx, job_id))
        return job_id, display_position

    try:
        result = _tx(tx) if tx is not None else get_connector().run_transaction(_tx)
        if tx is None:
            job_delegation.publish(changes)
        return result
    except RuntimeError:
        if tx is not None:
            raise
        return None, 0


def update_job_payload(job_id, queue_payload, *, get_connector: Callable[[], Any]):
    """Update the queue_payload column on an existing job."""
    get_connector().execute(
        "UPDATE jobs SET queue_payload = ? WHERE id = ?",
        (queue_payload, job_id),
    )


def dequeue_next_job(*, get_connector: Callable[[], Any], get_job_by_id: Callable):
    """Atomically take the oldest queued job and mark it running."""

    def _tx(tx):
        row = tx.query_one(
            """
            SELECT id FROM jobs
            WHERE status = 'queued' AND COALESCE(cancel_requested, 0) = 0
            ORDER BY COALESCE(priority, 100) DESC, COALESCE(queue_position, id) ASC, enqueued_at ASC, id ASC
            FETCH FIRST 1 ROWS ONLY
            """
        )
        if not row:
            return None
        job_id = int(row["id"])
        now = datetime.datetime.now()
        rowcount = tx.execute(
            """
            UPDATE jobs
            SET status = 'running', started_at = ?, queue_position = NULL
            WHERE id = ? AND status = 'queued' AND COALESCE(cancel_requested, 0) = 0
            """,
            (now, job_id),
        )
        if rowcount == 0:
            raise RuntimeError("dequeue race condition")
        return job_id

    try:
        job_id = get_connector().run_transaction(_tx)
    except RuntimeError:
        return None
    if job_id is None:
        return None
    return get_job_by_id(job_id)


def get_queued_jobs(
    limit=200, include_related=False, *, get_connector: Callable[[], Any]
):
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 200
    if limit <= 0:
        return []
    limit = min(limit, 1000)

    rows = [
        dict(r)
        for r in get_connector().query(
            """
        SELECT
            j.*,
            p.name AS phase_name,
            ph.selected_phases,
            ph.dependency_blockers
        FROM jobs j
        LEFT JOIN pipeline_phases p ON p.id = j.phase_id
        LEFT JOIN (
            SELECT
                jp.job_id,
                LIST(jp.phase_code, ', ') AS selected_phases,
                LIST(CASE WHEN jp.state IN ('blocked', 'waiting', 'pending_dependency') THEN jp.phase_code ELSE NULL END, ', ') AS dependency_blockers
            FROM job_phases jp
            GROUP BY jp.job_id
        ) ph ON ph.job_id = j.id
        WHERE j.status IN ('queued', 'paused', 'failed')
          AND (? = 1 OR j.status = 'queued')
        ORDER BY
            CASE j.status WHEN 'queued' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,
            COALESCE(j.priority, 100) DESC,
            COALESCE(j.queue_position, j.id) ASC,
            j.enqueued_at ASC,
            j.id ASC
        FETCH FIRST ? ROWS ONLY
        """,
            (1 if include_related else 0, limit),
        )
    ]

    avg_seconds = 120
    try:
        avg_row = get_connector().query_one(
            """
            SELECT AVG(DATEDIFF(SECOND FROM started_at TO completed_at)) AS avg_sec
            FROM jobs
            WHERE status = 'completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL
            """
        )
        if avg_row and avg_row.get("avg_sec"):
            avg_seconds = max(15, int(avg_row["avg_sec"]))
    except Exception:
        pass

    queue_idx = 0
    now = datetime.datetime.now()
    for row in rows:
        if row.get("status") in ("queued", "paused"):
            queue_idx += 1
            row["queue_position"] = queue_idx
            eta = now + datetime.timedelta(seconds=(queue_idx - 1) * avg_seconds)
            row["estimated_start"] = eta.isoformat(sep=" ", timespec="seconds")
        else:
            row["queue_position"] = "-"
            row["estimated_start"] = "-"
        row["target_scope"] = row.get("target_scope") or row.get("input_path") or "-"
        row["selected_phases"] = (
            row.get("selected_phases")
            or row.get("phase_name")
            or row.get("job_type")
            or "-"
        )
        row["dependency_blockers"] = row.get("dependency_blockers") or "None"
        row["retry_count"] = int(row.get("retry_count") or 0)
        row["priority"] = int(row.get("priority") or 100)
    return rows


def get_queued_jobs_count(*, get_connector: Callable[[], Any]) -> int:
    """
    Lightweight queue depth for JobDispatcher logging.

    Must never raise (dispatcher runs in a background thread).
    """
    try:
        row = get_connector().query_one(
            "SELECT COUNT(*) AS cnt FROM jobs WHERE status = 'queued'"
        )
        if not row:
            return 0
        return int(row.get("cnt") or 0)
    except Exception:
        return 0


def bump_job_priority(job_id, delta=10, *, get_connector: Callable[[], Any]):
    """Increase/decrease job priority for queued/paused jobs."""
    try:
        d = int(delta)
    except Exception:
        d = 10

    def _tx(tx):
        rowcount = tx.execute(
            """
            UPDATE jobs
            SET priority = CASE
                WHEN COALESCE(priority, 100) + ? < 1 THEN 1
                WHEN COALESCE(priority, 100) + ? > 999 THEN 999
                ELSE COALESCE(priority, 100) + ?
            END
            WHERE id = ? AND status IN ('queued', 'paused')
            """,
            (d, d, d, job_id),
        )
        if rowcount > 0:
            row = tx.query_one("SELECT priority FROM jobs WHERE id = ?", (job_id,))
            new_priority = (
                int(row["priority"]) if row and row["priority"] is not None else 100
            )
        else:
            new_priority = None
        return {"success": rowcount > 0, "priority": new_priority}

    return get_connector().run_transaction(_tx)


def set_job_priority(job_id, priority, *, get_connector: Callable[[], Any]):
    """Update job priority for queued/paused jobs."""
    try:
        p = max(1, min(int(priority), 999))
    except Exception:
        p = 100
    rowcount = get_connector().execute(
        "UPDATE jobs SET priority = ? WHERE id = ? AND status IN ('queued', 'paused')",
        (p, job_id),
    )
    return {"success": rowcount > 0, "priority": p}


def pause_queue_job(job_id, *, get_connector: Callable[[], Any]):
    """Pause a queued job so it is temporarily skipped by dequeue."""
    from modules.db_operations import job_delegation

    now = datetime.datetime.now()
    changes = []

    def pause(tx):
        job_delegation.lock_chain(tx, job_id)
        rowcount = tx.execute(
            "UPDATE jobs SET status = 'paused', paused_at = ? WHERE id = ? AND status = 'queued'",
            (now, job_id),
        )
        if rowcount:
            changes.extend(job_delegation.propagate(tx, job_id))
        return rowcount

    rowcount = get_connector().run_transaction(pause)
    job_delegation.publish(changes)
    return {"success": rowcount > 0}


def restart_failed_job(
    job_id, *, get_connector: Callable[[], Any], resume_job_phases: Callable
):
    """Move failed job back to queued and increment retry_count.

    Resets incomplete ``job_phases`` rows (same idea as ``resume_job_phases``) so a
    multi-phase run can retry phases that were ``failed`` / ``pending`` instead of
    staying stuck with no ``running`` phase row after dequeue.
    """
    now = datetime.datetime.now()
    rowcount = get_connector().execute(
        """
        UPDATE jobs
        SET status = 'queued', cancel_requested = 0, enqueued_at = ?, queue_position = id,
            retry_count = COALESCE(retry_count, 0) + 1, paused_at = NULL,
            started_at = NULL, finished_at = NULL, completed_at = NULL
        WHERE id = ? AND status = 'failed'
        """,
        (now, job_id),
    )
    if rowcount > 0:
        resume_job_phases(job_id)
    return {"success": rowcount > 0}


def request_cancel_job(job_id, *, get_connector: Callable[[], Any]):
    from modules.db_operations import job_delegation

    now = datetime.datetime.now()
    changes = []

    def _tx(tx):
        job_delegation.lock_chain(tx, job_id)
        row = tx.query_one("SELECT status FROM jobs WHERE id = ?", (job_id,))
        if not row:
            return {"success": False, "reason": "not_found"}
        status = (row["status"] or "").strip().lower()
        if status in ("completed", "failed", "cancelled"):
            return {"success": False, "reason": "already_finished", "status": status}
        if status == "running":
            return {
                "success": False,
                "reason": "running_not_supported",
                "status": status,
            }
        if status not in ("queued", "paused"):
            return {
                "success": False,
                "reason": "not_cancellable_state",
                "status": status,
            }
        rowcount = tx.execute(
            """
            UPDATE jobs
            SET status = 'cancelled', cancel_requested = 1, queue_position = NULL,
                finished_at = ?, completed_at = ?
            WHERE id = ? AND status IN ('queued', 'paused')
            """,
            (now, now, job_id),
        )
        if rowcount == 0:
            latest = tx.query_one("SELECT status FROM jobs WHERE id = ?", (job_id,))
            latest_status = (
                (latest["status"] or "").strip().lower() if latest else "not_found"
            )
            if latest_status == "running":
                return {
                    "success": False,
                    "reason": "running_not_supported",
                    "status": latest_status,
                }
            if latest_status in ("completed", "failed", "cancelled"):
                return {
                    "success": False,
                    "reason": "already_finished",
                    "status": latest_status,
                }
            if latest_status == "not_found":
                return {"success": False, "reason": "not_found"}
            return {
                "success": False,
                "reason": "cancel_failed",
                "status": latest_status,
            }
        tx.execute(
            "UPDATE job_phases SET state = 'cancelled', completed_at = ? "
            "WHERE job_id = ? AND state NOT IN ('completed', 'skipped')", (now, job_id),
        )
        changes.extend(job_delegation.propagate(tx, job_id))
        return {"success": True, "reason": "cancelled", "status": status}

    result = get_connector().run_transaction(_tx)
    job_delegation.publish(changes)
    return result
