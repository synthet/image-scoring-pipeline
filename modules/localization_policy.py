"""Which images localization may pick up automatically (#527, rollout stage 4).

With ``localization.new_images_only`` on (the default), planned localization work is limited
to *new* images (indexed at or after the persisted enablement boundary) and images whose
source identity changed since their current run. Unchanged legacy images are left to an
explicit image selection or the legacy import, so enabling the phase never rescans the
library.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from modules.localization import DETECTOR_KEY, STATUS_RETRYABLE

logger = logging.getLogger(__name__)

_CHUNK = 1000

#: Bounded repair (#527): automatic attempts per artifact identity, and the wait after the
#: first and second failure. A third failure exhausts the identity.
REPAIR_MAX_ATTEMPTS = 3
REPAIR_BACKOFF_SECONDS = (60, 300)

#: A detector outage is a lane problem, not an image problem: it never counts as an attempt.
OUTAGE_ERROR_CODE = "detector_unavailable"

#: Run history read per image; more than the attempt limit so outage rows can be skipped.
_HISTORY_DEPTH = 20


def ensure_enablement_boundary(detector_key: str = DETECTOR_KEY) -> Any:
    """Return ``enabled_at`` for ``detector_key``, writing it now if it is not set yet."""
    from modules import db

    conn = db.get_connector()
    conn.execute(
        "INSERT INTO localization_enablement (detector_key) VALUES (?) "
        "ON CONFLICT (detector_key) DO NOTHING",
        (detector_key,),
    )
    row = conn.query_one(
        "SELECT enabled_at FROM localization_enablement WHERE detector_key = ?",
        (detector_key,),
    )
    return (row or {}).get("enabled_at")


def _source_changed(row: dict[str, Any]) -> bool:
    """True when the file no longer matches the current run's source identity."""
    from modules.rendition import source_identity

    if not row.get("source_hash"):
        return False  # legacy import or an outage run: nothing to compare against
    try:
        current = source_identity(row.get("file_path") or "")
    except OSError:
        return False
    return current != (row.get("source_hash"), row.get("source_hash_version"))


def filter_auto_eligible(image_ids: list[int]) -> list[int]:
    """Keep new images and images whose source changed; drop unchanged legacy images.

    Order is preserved. A new image is one whose ``images.registered_at`` is at or after the
    boundary; a NULL ``registered_at`` counts as legacy. Not ``created_at``: indexing stores
    the capture time there (#584).
    """
    from modules import db

    ids = [int(i) for i in image_ids or []]
    if not ids:
        return []
    ensure_enablement_boundary()

    keep: set[int] = set()
    conn = db.get_connector()
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start:start + _CHUNK]
        placeholders = ",".join("?" * len(chunk))
        rows = conn.query(
            f"""
            SELECT i.id, i.file_path,
                   (le.enabled_at IS NOT NULL AND i.registered_at IS NOT NULL
                    AND i.registered_at >= le.enabled_at) AS is_new,
                   r.source_hash, r.source_hash_version
            FROM images i
            LEFT JOIN localization_enablement le ON le.detector_key = ?
            LEFT JOIN image_localization_runs r
                   ON r.image_id = i.id AND r.detector_key = ? AND r.is_current
            WHERE i.id IN ({placeholders})
            """,
            tuple([DETECTOR_KEY, DETECTOR_KEY] + chunk),
        ) or []
        for row in rows:
            if row.get("is_new") or _source_changed(row):
                keep.add(int(row["id"]))

    dropped = len(ids) - len(keep)
    if dropped:
        logger.info("localization: new_images_only left out %d unchanged legacy image(s)", dropped)
    return [i for i in ids if i in keep]


# ---------------------------------------------------------------------------
# Bounded repair (#527)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RepairState:
    attempts: int = 0
    wait_seconds: float = 0.0

    @property
    def exhausted(self) -> bool:
        return self.attempts >= REPAIR_MAX_ATTEMPTS

    @property
    def blocked(self) -> bool:
        return self.exhausted or self.wait_seconds > 0


def _identity(row: dict[str, Any]) -> tuple:
    return (row.get("detector_config_hash"), row.get("source_hash"), row.get("source_hash_version"))


def repair_state(history: list[dict[str, Any]], identity: tuple | None = None) -> RepairState:
    """Attempts and remaining backoff for one image, from its runs newest first.

    An attempt is a ``retryable_error`` run; consecutive ones with the same
    ``(detector_config_hash, source_hash, source_hash_version)`` share an artifact identity.
    Outage runs are skipped. Any other status ends the streak. ``identity`` is the identity
    the next attempt would have: when it differs from the streak's, the count starts over.
    Each row needs ``age_seconds`` (time since ``attempted_at``, measured by the database).
    """
    attempts = 0
    streak: tuple | None = None
    newest_age = 0.0
    for row in history:
        if row.get("error_code") == OUTAGE_ERROR_CODE:
            continue
        if row.get("status") != STATUS_RETRYABLE:
            break
        if streak is None:
            streak = _identity(row)
            newest_age = float(row.get("age_seconds") or 0.0)
        elif _identity(row) != streak:
            break
        attempts += 1
    if attempts == 0 or (identity is not None and identity != streak):
        return RepairState()
    if attempts >= REPAIR_MAX_ATTEMPTS:
        return RepairState(attempts=attempts)
    wait = REPAIR_BACKOFF_SECONDS[attempts - 1] - newest_age
    return RepairState(attempts=attempts, wait_seconds=max(0.0, wait))


def fetch_run_history(image_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """Recent runs per image, newest first, each with ``age_seconds``."""
    from modules import db

    ids = [int(i) for i in image_ids or []]
    out: dict[int, list[dict[str, Any]]] = {}
    conn = db.get_connector()
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start:start + _CHUNK]
        placeholders = ",".join("?" * len(chunk))
        rows = conn.query(
            f"""
            SELECT image_id, status, error_code, detector_config_hash, source_hash,
                   source_hash_version, age_seconds
            FROM (
                SELECT image_id, status, error_code, detector_config_hash, source_hash,
                       source_hash_version,
                       EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - attempted_at)) AS age_seconds,
                       ROW_NUMBER() OVER (PARTITION BY image_id
                                          ORDER BY attempted_at DESC, id DESC) AS rn
                FROM image_localization_runs
                WHERE detector_key = ? AND image_id IN ({placeholders})
            ) h
            WHERE rn <= ?
            ORDER BY image_id, rn
            """,
            tuple([DETECTOR_KEY] + chunk + [_HISTORY_DEPTH]),
        ) or []
        for row in rows:
            out.setdefault(int(row["image_id"]), []).append(row)
    return out
