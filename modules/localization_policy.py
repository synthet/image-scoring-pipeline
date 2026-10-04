"""Which images localization may pick up automatically (#527, rollout stage 4).

With ``localization.new_images_only`` on (the default), planned localization work is limited
to *new* images (indexed at or after the persisted enablement boundary) and images whose
source identity changed since their current run. Unchanged legacy images are left to an
explicit image selection or the legacy import, so enabling the phase never rescans the
library.
"""

from __future__ import annotations

import logging
from typing import Any

from modules.localization import DETECTOR_KEY

logger = logging.getLogger(__name__)

_CHUNK = 1000


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

    Order is preserved. A new image is one whose ``images.created_at`` is at or after the
    boundary; a NULL ``created_at`` counts as legacy.
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
                   (le.enabled_at IS NOT NULL AND i.created_at IS NOT NULL
                    AND i.created_at >= le.enabled_at) AS is_new,
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
