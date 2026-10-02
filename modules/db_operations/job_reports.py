"""Job execution reports, per-image actions, and phase counters."""

import json
from collections.abc import Callable
from typing import Any


def insert_job_image_actions(
    actions: list[dict], *, get_connector: Callable[[], Any]
) -> None:
    """Batch insert into ``job_image_actions``. Called by ReportCollector.flush().

    Uses a multi-row INSERT for efficiency (one round-trip per batch).
    Postgres-only (``?::jsonb`` cast).
    """
    if not actions:
        return
    conn = get_connector()
    value_groups = []
    params: list = []
    for row in actions:
        value_groups.append("(?, ?, ?, ?, ?, ?::jsonb, ?::jsonb)")
        params.extend(
            [
                row["job_id"],
                row["image_id"],
                row["phase_code"],
                row["action"],
                row.get("reason"),
                json.dumps(row["before_snapshot"])
                if row.get("before_snapshot") is not None
                else None,
                json.dumps(row["after_snapshot"])
                if row.get("after_snapshot") is not None
                else None,
            ]
        )
    sql = (
        "INSERT INTO job_image_actions "
        "(job_id, image_id, phase_code, action, reason, before_snapshot, after_snapshot) "
        "VALUES " + ", ".join(value_groups)
    )
    conn.execute(sql, tuple(params))


def save_job_report(
    job_id: int, report: dict, *, get_connector: Callable[[], Any]
) -> None:
    """Write ``report_json`` JSONB to the jobs table."""
    get_connector().execute(
        "UPDATE jobs SET report_json = ?::jsonb WHERE id = ?",
        (json.dumps(report), int(job_id)),
    )


def get_job_report(job_id: int, *, get_connector: Callable[[], Any]) -> dict | None:
    """Read ``report_json`` from the jobs table."""
    row = get_connector().query_one(
        "SELECT report_json FROM jobs WHERE id = ?",
        (int(job_id),),
    )
    if not row:
        return None
    raw = row.get("report_json")
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(raw, dict):
        return raw
    return None


def get_job_image_actions(
    job_id: int,
    phase_code: str | None = None,
    action: str | None = None,
    offset: int = 0,
    limit: int = 50,
    *,
    get_connector: Callable[[], Any],
) -> dict:
    """Query ``job_image_actions`` with filtering and pagination.

    Returns ``{"items": [...], "total": int}``.
    """
    jid = int(job_id)
    where = ["jia.job_id = ?"]
    params: list = [jid]

    if phase_code:
        where.append("LOWER(TRIM(jia.phase_code)) = ?")
        params.append(phase_code.strip().lower())
    if action:
        where.append("LOWER(TRIM(jia.action)) = ?")
        params.append(action.strip().lower())

    where_sql = " AND ".join(where)
    conn = get_connector()

    # Total count.
    count_row = conn.query_one(
        f"SELECT COUNT(*) AS c FROM job_image_actions jia WHERE {where_sql}",
        tuple(params),
    )
    total = int(
        (count_row.get("c") or count_row.get("COUNT(*)") or 0) if count_row else 0
    )

    # Paginated items with file_path join.
    rows = conn.query(
        f"""
        SELECT jia.id, jia.image_id, i.file_path, jia.phase_code, jia.action,
               jia.reason, jia.before_snapshot, jia.after_snapshot, jia.created_at
        FROM job_image_actions jia
        LEFT JOIN images i ON i.id = jia.image_id
        WHERE {where_sql}
        ORDER BY jia.id
        OFFSET ? LIMIT ?
        """,
        tuple(params) + (offset, limit),
    )

    items = []
    for r in rows or []:
        before = r.get("before_snapshot")
        after = r.get("after_snapshot")
        if isinstance(before, str):
            try:
                before = json.loads(before)
            except Exception:
                pass
        if isinstance(after, str):
            try:
                after = json.loads(after)
            except Exception:
                pass
        items.append(
            {
                "id": r.get("id"),
                "image_id": r.get("image_id"),
                "file_path": r.get("file_path"),
                "phase_code": (r.get("phase_code") or "").strip(),
                "action": (r.get("action") or "").strip(),
                "reason": r.get("reason"),
                "before_snapshot": before,
                "after_snapshot": after,
                "created_at": str(r.get("created_at") or ""),
            }
        )

    return {"items": items, "total": total}


def update_job_phase_counters(
    job_id: int,
    phase_code: str,
    *,
    in_scope: int = 0,
    targeted: int = 0,
    processed: int = 0,
    skipped: int = 0,
    failed: int = 0,
    get_connector: Callable[[], Any],
) -> None:
    """Update counter columns on a ``job_phases`` row."""
    get_connector().execute(
        """
        UPDATE job_phases
        SET images_in_scope = ?,
            images_targeted = ?,
            images_processed = ?,
            images_skipped = ?,
            images_failed = ?
        WHERE job_id = ? AND LOWER(TRIM(phase_code)) = ?
        """,
        (
            in_scope,
            targeted,
            processed,
            skipped,
            failed,
            int(job_id),
            phase_code.strip().lower(),
        ),
    )
