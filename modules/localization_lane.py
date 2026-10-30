"""Automatic localization repair lane (#527, rollout stage 4).

Localization is never a folder bucket in auto-drive (``DEFAULT_TARGET_PHASES`` leaves it out),
so it can never be the earliest blocking bucket and core scoring/culling/keywords never wait
for it. Instead, when ``localization.repair.enabled`` is on, the job dispatcher calls
:func:`maybe_enqueue` on its idle path. It admits at most one localization job, and only
while no pipeline job is queued or running, so repair cannot starve ingestion.

A lane job is a selector job of up to ``LANE_BATCH`` images with
``localization_lane: "auto"`` in its payload, which turns on the bounded-repair limit in
the runner. Candidates are:

- new images (indexed at or after the enablement boundary) with no localization run yet;
- images whose current run is a ``retryable_error`` that is not exhausted or cooling down.

Source-changed legacy images are picked up by folder submits (``new_images_only``), not here:
finding them needs a file read per localized image.

A detector outage holds the whole lane rather than spending per-image attempts: 1 min after
the first outage job, then 5 min after each later one. While the outage streak lasts, each
admitted lane job is a one-image canary; the first clean canary clears the streak and full
batches resume, so recovery never needs a process restart (#706).

Under active authority a lane job may also carry targeted negative recovery: a current
``no_detection`` run with independent bird discovery evidence is re-detected once per
detector-config/source/policy identity. A repeat negative ends it; faults use the bounded
retry path above.

Under active localization authority the same idle slot also admits queued GPU species work
(``classify``/``fallback``) as a ``bird_species`` job, after detection candidates. CPU species
actions never wait for it: the authority worker runs them independently of GPU activity.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any

from modules.localization import DETECTOR_KEY, STATUS_NO_DETECTION, STATUS_RETRYABLE
from modules.localization_policy import (
    OUTAGE_ERROR_CODE,
    REPAIR_BACKOFF_SECONDS,
    fetch_run_history,
    repair_state,
)

logger = logging.getLogger(__name__)

LANE_BATCH = 500
SPECIES_BATCH = 200
LANE_TICK_SEC = 60.0
#: Retryable candidates inspected per tick; bounds the history query on a failing library.
_RETRYABLE_SCAN = 5000
_ACTIVE_JOB_STATUSES = ("queued", "running", "pending", "paused", "restarting")

_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "last_tick_at": 0.0,
    "last_job_id": None,
    "last_job_kind": None,
    "outage_streak": 0,
    "hold_until": 0.0,
    "backlog": None,
}


def reset_state() -> None:
    """Forget the lane hold and last job (tests; a process restart does the same)."""
    with _LOCK:
        _STATE.update(last_tick_at=0.0, last_job_id=None, last_job_kind=None, outage_streak=0, hold_until=0.0,
                      backlog=None)


def get_state() -> dict[str, Any]:
    with _LOCK:
        return dict(_STATE)


def get_diagnostic_state(now: float | None = None) -> dict[str, Any]:
    """JSON-safe, process-local snapshot; never tick or clear an outage hold."""
    state = get_state()
    now = time.time() if now is None else now
    until = state["hold_until"]
    indefinite = math.isinf(until)
    held = now < until
    state.update(
        source="process_local",
        canary_pending=state["outage_streak"] > 0,
        hold_until=None if indefinite else until,
        hold_reason="detector_outage_hold" if held else None,
        hold_seconds_remaining=None if indefinite else max(0.0, until - now),
        restart_required=held and indefinite,
    )
    if state["backlog"] is not None:
        state["backlog"] = dict(state["backlog"])
    return state


def lane_enabled() -> bool:
    from modules.localization import localization_config, repair_enabled
    from modules.phases import is_phase_enabled

    return is_phase_enabled("localization") and repair_enabled(localization_config())


def species_lane_active() -> bool:
    """Active authority admits queued GPU species work through this lane. Never raises."""
    from modules import db

    try:
        row = db.get_connector().query_one("SELECT mode FROM localization_authority_control WHERE id = 1") or {}
    except Exception:
        return False
    return row.get("mode") == "active"


def select_species_candidates(limit: int = SPECIES_BATCH) -> list[int]:
    """Images with GPU species work a ``SpeciesStore.claim_next`` call would pick now."""
    from modules import db
    from modules.localization_species import GPU_ACTIONS

    rows = db.get_connector().query(
        "SELECT DISTINCT image_id FROM localization_species_work WHERE action IN (?, ?) AND attempts < 3 "
        "AND available_at <= clock_timestamp() AND (status = 'queued' OR "
        "(status = 'running' AND lease_until <= clock_timestamp())) ORDER BY image_id FETCH FIRST ? ROWS ONLY",
        (*GPU_ACTIONS, int(limit)),
    ) or []
    return [int(r["image_id"]) for r in rows]


#: Identity of one recovery sequence: the current run's detector config and source, plus the
#: active approved policies. A changed identity permits one new sequence.
_RECOVERY_IDENTITY = """
    r.detector_config_hash, COALESCE(r.source_hash, ''), COALESCE(r.source_hash_version, ''),
    COALESCE((SELECT string_agg(a.policy_hash || ':' || a.revision::text, ',' ORDER BY a.policy_hash)
              FROM localization_policy_approvals a WHERE a.active), '')
"""


def select_recovery_candidates(limit: int, exclude: list[int] | tuple = ()) -> list[int]:
    """Discovery-positive current negatives that have not had recovery for their identity."""
    from modules import db

    skip = {int(i) for i in exclude}
    rows = db.get_connector().query(
        "SELECT r.image_id FROM image_localization_runs r "
        "WHERE r.detector_key = ? AND r.is_current AND r.status = ? "
        "AND EXISTS (SELECT 1 FROM localization_discovery_evidence d WHERE d.image_id = r.image_id AND d.independent) "
        "AND NOT EXISTS (SELECT 1 FROM localization_recovery_attempts m WHERE m.image_id = r.image_id "
        "AND m.detector_key = r.detector_key AND (m.detector_config_hash, m.source_hash, m.source_hash_version, "
        f"m.policy_key) = ({_RECOVERY_IDENTITY})) ORDER BY r.image_id FETCH FIRST ? ROWS ONLY",
        (DETECTOR_KEY, STATUS_NO_DETECTION, int(limit) + len(skip)),
    ) or []
    return [i for i in (int(r["image_id"]) for r in rows) if i not in skip][:limit]


def _mark_recovery(image_ids: list[int]) -> None:
    """Record the scheduled sequence so a repeat negative for the same identity ends recovery."""
    from modules import db

    placeholders = ",".join("?" * len(image_ids))
    db.get_connector().execute(
        "INSERT INTO localization_recovery_attempts (image_id, detector_key, detector_config_hash, source_hash, "
        f"source_hash_version, policy_key) SELECT r.image_id, r.detector_key, {_RECOVERY_IDENTITY} "
        f"FROM image_localization_runs r WHERE r.detector_key = ? AND r.is_current AND r.image_id IN ({placeholders}) "
        "ON CONFLICT DO NOTHING",
        (DETECTOR_KEY, *[int(i) for i in image_ids]),
    )


def _core_idle() -> bool:
    """No pipeline job queued or running, and no localization job anywhere in flight."""
    from modules import db

    if db.get_queued_jobs_count() > 0:
        return False
    if db.count_running_pipeline_jobs(exclude_maintenance=True) > 0:
        return False
    rows = db.get_jobs(limit=30, offset=0, status_filter=_ACTIVE_JOB_STATUSES) or []
    return not any((r.get("job_type") or "").strip().lower() == "localization" for r in rows)


def _note_finished_job(now: float) -> None:
    """Update the outage hold from the last lane job once it is terminal."""
    from modules import db

    job_id = _STATE["last_job_id"]
    if job_id is None:
        return
    job = db.get_job(job_id) or {}
    if (job.get("status") or "").strip().lower() in _ACTIVE_JOB_STATUSES:
        return
    if _STATE["last_job_kind"] == "species":
        _STATE["last_job_id"] = None  # species jobs say nothing about detector availability
        return
    row = db.get_connector().query_one(
        "SELECT COUNT(*) AS n FROM image_localization_runs WHERE job_id = ? AND error_code = ?",
        (int(job_id), OUTAGE_ERROR_CODE),
    ) or {}
    _STATE["last_job_id"] = None
    if int(row.get("n") or 0) == 0:
        _STATE["outage_streak"] = 0
        return
    _STATE["outage_streak"] += 1
    streak = _STATE["outage_streak"]
    hold = REPAIR_BACKOFF_SECONDS[min(streak, len(REPAIR_BACKOFF_SECONDS)) - 1]
    _STATE["hold_until"] = now + hold
    logger.warning("localization lane: detector unavailable on %d lane job(s); holding %ds, then a one-image canary",
                   streak, hold)


def select_candidates(limit: int = LANE_BATCH) -> tuple[list[int], dict[str, int]]:
    """Return ``(image_ids, backlog)`` for one lane job.

    ``backlog`` is reported separately from core completion:
    ``{"new", "retryable", "cooling_down", "exhausted", "pending"}``. ``retryable`` counts
    current retryable runs; the cooling/exhausted split covers at most ``_RETRYABLE_SCAN``.
    """
    from modules import db
    from modules.localization_policy import ensure_enablement_boundary

    ensure_enablement_boundary()
    conn = db.get_connector()
    metadata_done = """
        EXISTS (SELECT 1 FROM image_phase_status ms
                JOIN pipeline_phases pm ON pm.id = ms.phase_id
                WHERE ms.image_id = i.id AND LOWER(TRIM(pm.code)) = 'metadata'
                  AND LOWER(TRIM(ms.status)) IN ('done', 'skipped'))
    """
    new_sql = f"""
        FROM images i
        JOIN localization_enablement le ON le.detector_key = ?
        WHERE i.registered_at >= le.enabled_at AND {metadata_done}
          AND NOT EXISTS (SELECT 1 FROM image_localization_runs r
                          WHERE r.image_id = i.id AND r.detector_key = ? AND r.is_current)
    """
    retry_sql = f"""
        FROM images i
        JOIN image_localization_runs r
          ON r.image_id = i.id AND r.detector_key = ? AND r.is_current AND r.status = ?
        WHERE {metadata_done}
    """
    new_n = int((conn.query_one(f"SELECT COUNT(*) AS n {new_sql}", (DETECTOR_KEY, DETECTOR_KEY)) or {}).get("n") or 0)
    retry_n = int((conn.query_one(f"SELECT COUNT(*) AS n {retry_sql}", (DETECTOR_KEY, STATUS_RETRYABLE))
                   or {}).get("n") or 0)

    new_ids = [int(r["id"]) for r in conn.query(
        f"SELECT i.id {new_sql} ORDER BY i.id FETCH FIRST ? ROWS ONLY", (DETECTOR_KEY, DETECTOR_KEY, int(limit)),
    ) or []]
    retry_ids = [int(r["id"]) for r in conn.query(
        f"SELECT i.id {retry_sql} ORDER BY i.id FETCH FIRST ? ROWS ONLY",
        (DETECTOR_KEY, STATUS_RETRYABLE, _RETRYABLE_SCAN),
    ) or []]

    history = fetch_run_history(retry_ids)
    ready: list[int] = []
    cooling = exhausted = 0
    for image_id in retry_ids:
        state = repair_state(history.get(image_id) or [])
        if state.exhausted:
            exhausted += 1
        elif state.blocked:
            cooling += 1
        else:
            ready.append(image_id)

    backlog = {
        "new": new_n,
        "retryable": retry_n,
        "cooling_down": cooling,
        "exhausted": exhausted,
        "pending": new_n + max(0, retry_n - cooling - exhausted),
    }
    return (new_ids + ready)[:limit], backlog


def _enqueue(image_ids: list[int], recovery_ids: list[int] | tuple = ()) -> int | None:
    from modules import db
    from modules.job_description import augment_queue_payload_for_audit
    from modules.phases import PhaseCode, job_type_for_phase

    body: dict[str, Any] = {
        "input_path": None,
        "resolved_image_ids": list(image_ids),
        "resolved_image_ids_by_stage": {"localization": list(image_ids)},
        "localization_lane": "auto",
    }
    if recovery_ids:
        body["localization_recovery_ids"] = list(recovery_ids)
    payload = augment_queue_payload_for_audit(
        body,
        trigger="api",  # same trigger the auto-drive's own enqueues use
        tool_id="localization_lane",
    )
    job_id, _ = db.enqueue_job_with_phases(
        "SELECTOR_LOCALIZATION_LANE",
        phase_code=PhaseCode.LOCALIZATION.value,
        job_type=job_type_for_phase(PhaseCode.LOCALIZATION),
        queue_payload=payload,
        description=f"Localization repair lane: {len(image_ids)} image(s)",
        phase_codes=[PhaseCode.LOCALIZATION.value],
    )
    return int(job_id) if job_id else None


def _enqueue_species(image_ids: list[int]) -> int | None:
    from modules import db
    from modules.job_description import augment_queue_payload_for_audit
    from modules.phases import PhaseCode, job_type_for_phase

    payload = augment_queue_payload_for_audit(
        {
            "input_path": None,
            "resolved_image_ids": list(image_ids),
            "resolved_image_ids_by_stage": {"bird_species": list(image_ids)},
            "species_lane": "auto",
        },
        trigger="api",
        tool_id="localization_lane",
    )
    job_id, _ = db.enqueue_job_with_phases(
        "SELECTOR_SPECIES_LANE",
        phase_code=PhaseCode.BIRD_SPECIES.value,
        job_type=job_type_for_phase(PhaseCode.BIRD_SPECIES),
        queue_payload=payload,
        description=f"Species authority lane: {len(image_ids)} image(s)",
        phase_codes=[PhaseCode.BIRD_SPECIES.value],
    )
    return int(job_id) if job_id else None


def maybe_enqueue(now: float | None = None) -> dict[str, Any]:
    """Admit at most one lane job when the lane is on and core work is idle. Never raises."""
    now = time.time() if now is None else now
    out: dict[str, Any] = {"enqueued": None}
    try:
        detect = lane_enabled()
        species = species_lane_active()
        if not detect and not species:
            out["skipped"] = "disabled"
            return out
        with _LOCK:
            if now - _STATE["last_tick_at"] < LANE_TICK_SEC:
                out["skipped"] = "cooldown"
                return out
            _STATE["last_tick_at"] = now
            _note_finished_job(now)
            if _STATE["last_job_id"] is not None:
                out["skipped"] = "lane_job_active"
                return out
            if now < _STATE["hold_until"]:
                out["skipped"] = "detector_outage_hold"
                return out
        if not _core_idle():
            out["skipped"] = "core_busy"
            return out
        canary = get_state()["outage_streak"] > 0
        image_ids: list[int] = []
        if detect:
            limit = 1 if canary else LANE_BATCH
            image_ids, backlog = select_candidates(limit)
            image_ids = image_ids[:limit]
            out["backlog"] = backlog
            with _LOCK:
                _STATE["backlog"] = backlog
        recovery: list[int] = []
        if detect and species and len(image_ids) < limit:
            recovery = select_recovery_candidates(limit - len(image_ids), exclude=image_ids)
        if not image_ids and not recovery:
            species_ids = select_species_candidates() if species else []
            if not species_ids:
                out["skipped"] = "no_candidates"
                return out
            job_id = _enqueue_species(species_ids)
            with _LOCK:
                _STATE.update(last_job_id=job_id, last_job_kind="species")
            out.update(enqueued=job_id, kind="species")
            logger.info("localization lane: enqueued species job %s with %d image(s)", job_id, len(species_ids))
            return out
        job_id = _enqueue(image_ids + recovery, recovery) if recovery else _enqueue(image_ids)
        if job_id and recovery:
            _mark_recovery(recovery)
        with _LOCK:
            _STATE.update(last_job_id=job_id, last_job_kind="localization")
        out.update(enqueued=job_id, kind="localization", recovery=len(recovery))
        logger.info("localization lane: enqueued %sjob %s with %d image(s); backlog %s",
                    "canary " if canary else "", job_id, len(image_ids), backlog)
    except Exception:
        logger.exception("localization lane: tick failed")
        out["skipped"] = "error"
    return out
