#!/usr/bin/env python3
"""
Queue localization for images whose ``images.bird_bbox`` has never been set.

This script no longer runs a detector or writes ``bird_bbox`` (#638, rollout Stage 8: no
supported writer updates ``bird_bbox`` without a normalized run). It selects the same
candidates as before and enqueues ID-scoped localization jobs for them, so each image gets a
normalized ``image_localization_runs`` row. ``bird_bbox`` is then written only by the
selection projection (``modules/localization_selection.py``) when a run is promoted.
Images that already have a current ``bird`` run are skipped: their box waits on promotion,
not on another detection.

The jobs are explicit submits, not the automatic repair lane, so the lane's bounded-repair
limit does not apply. WebUI must be running to execute them.

Usage (gpu-shell, per CLAUDE.md):
  # Inspect how many rows would be queued
  python scripts/backfill_bird_bbox.py --dry-run

  # One folder
  python scripts/backfill_bird_bbox.py --folder "/path/to/folder"

  # Every image with bird_bbox IS NULL (no birds* keyword filter)
  python scripts/backfill_bird_bbox.py --all-null
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import List

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_SQL_MISSING_BBOX = """
SELECT i.id, i.file_path, i.thumbnail_path, i.thumbnail_path_win
FROM images i
JOIN folders f ON i.folder_id = f.id
WHERE i.bird_bbox IS NULL
  AND EXISTS (
    SELECT 1 FROM image_keywords ik
    JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
    WHERE ik.image_id = i.id AND kd.keyword_norm LIKE ?
  )
  AND (? = '' OR f.path = ?)
ORDER BY f.path, i.id
"""

#: Same as ``_SQL_MISSING_BBOX`` but no keyword gate — every ``bird_bbox IS NULL`` row.
_SQL_MISSING_BBOX_ALL = """
SELECT i.id, i.file_path, i.thumbnail_path, i.thumbnail_path_win
FROM images i
JOIN folders f ON i.folder_id = f.id
WHERE i.bird_bbox IS NULL
  AND (? = '' OR f.path = ?)
ORDER BY f.path, i.id
"""

_SQL_CURRENT_RUNS = """
SELECT DISTINCT image_id FROM image_localization_runs
WHERE detector_key = 'bird' AND is_current AND image_id IN ({placeholders})
"""

#: Queue one localization job per this many images (the lane's own batch is smaller).
DEFAULT_CHUNK_SIZE = 200


def fetch_candidates(*, folder: str = "", limit: int = 0, all_null: bool = False) -> List[dict]:
    """Return images with ``bird_bbox IS NULL``.

    By default only bird-tagged rows (``keyword_norm LIKE '%birds%'``).
    Pass ``all_null=True`` to include every null-bbox image (no keyword filter).
    """
    from modules import db

    conn = db.get_db()
    try:
        c = conn.cursor()
        folder_arg = (folder or "").strip()
        if all_null:
            c.execute(_SQL_MISSING_BBOX_ALL, (folder_arg, folder_arg))
        else:
            c.execute(_SQL_MISSING_BBOX, ("%birds%", folder_arg, folder_arg))
        rows = c.fetchall()
    finally:
        conn.close()

    out: List[dict] = []
    for row in rows:
        # Cursor may return tuple or dict-like depending on connector.
        if hasattr(row, "keys"):
            item = {
                "id": int(row["id"]),
                "file_path": row["file_path"],
                "thumbnail_path": row.get("thumbnail_path") if hasattr(row, "get") else row["thumbnail_path"],
                "thumbnail_path_win": (
                    row.get("thumbnail_path_win") if hasattr(row, "get") else row["thumbnail_path_win"]
                ),
            }
        else:
            item = {
                "id": int(row[0]),
                "file_path": row[1],
                "thumbnail_path": row[2] if len(row) > 2 else None,
                "thumbnail_path_win": row[3] if len(row) > 3 else None,
            }
        out.append(item)
        if limit > 0 and len(out) >= limit:
            break
    return out


def drop_already_localized(image_ids: List[int]) -> List[int]:
    """Remove images that already have a current ``bird`` localization run."""
    from modules import db

    conn = db.get_connector()
    localized: set[int] = set()
    for start in range(0, len(image_ids), 500):
        chunk = image_ids[start:start + 500]
        sql = _SQL_CURRENT_RUNS.format(placeholders=",".join("?" for _ in chunk))
        localized.update(int(row["image_id"]) for row in conn.query(sql, tuple(chunk)) or [])
    return [image_id for image_id in image_ids if image_id not in localized]


def enqueue_localization(image_ids: List[int], *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> List[int]:
    """Queue ID-scoped localization jobs in chunks. Returns the created ``jobs.id`` values."""
    from modules import db
    from modules.job_description import augment_queue_payload_for_audit
    from modules.phases import PhaseCode, job_type_for_phase

    job_ids: List[int] = []
    for start in range(0, len(image_ids), chunk_size):
        chunk = list(image_ids[start:start + chunk_size])
        payload = augment_queue_payload_for_audit(
            {
                "input_path": None,
                "resolved_image_ids": chunk,
                "resolved_image_ids_by_stage": {"localization": chunk},
            },
            trigger="api",
            tool_id="backfill_bird_bbox",
        )
        job_id, _ = db.enqueue_job_with_phases(
            "SELECTOR_LOCALIZATION_BACKFILL",
            phase_code=PhaseCode.LOCALIZATION.value,
            job_type=job_type_for_phase(PhaseCode.LOCALIZATION),
            queue_payload=payload,
            description=f"Localization backfill: {len(chunk)} image(s)",
            phase_codes=[PhaseCode.LOCALIZATION.value],
        )
        if not job_id:
            raise RuntimeError(f"failed to enqueue localization for {len(chunk)} image(s) at offset {start}")
        job_ids.append(int(job_id))
    return job_ids


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Query and print candidates; do not enqueue jobs",
    )
    p.add_argument(
        "--folder",
        type=str,
        default="",
        metavar="PATH",
        help="Limit to one folder path (exact match on folders.path)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Queue at most N images (0 = no limit)",
    )
    p.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        metavar="N",
        help=f"Images per localization job (default {DEFAULT_CHUNK_SIZE})",
    )
    p.add_argument(
        "--all-null",
        action="store_true",
        help="Include every bird_bbox IS NULL row (skip birds* keyword filter)",
    )
    args = p.parse_args(argv)

    if args.chunk_size < 1:
        logger.error("--chunk-size must be >= 1")
        return 2

    rows = fetch_candidates(folder=args.folder, limit=args.limit, all_null=args.all_null)
    scope = "image(s)" if args.all_null else "bird-tagged image(s)"
    logger.info(
        "Found %s %s with bird_bbox IS NULL%s",
        len(rows),
        scope,
        f" in folder {args.folder!r}" if args.folder else "",
    )
    image_ids = drop_already_localized([row["id"] for row in rows])
    if len(image_ids) < len(rows):
        logger.info("Skipping %s image(s) that already have a current localization run.", len(rows) - len(image_ids))

    if not image_ids:
        logger.warning("Nothing to queue.")
        return 1

    if args.dry_run:
        paths = {row["id"]: row["file_path"] for row in rows}
        for image_id in image_ids[:50]:
            print(f"{image_id}\t{paths[image_id]}")
        if len(image_ids) > 50:
            print(f"... and {len(image_ids) - 50} more", file=sys.stderr)
        logger.info("Dry-run: %s image(s) would be queued; nothing enqueued.", len(image_ids))
        return 0

    job_ids = enqueue_localization(image_ids, chunk_size=args.chunk_size)
    logger.info("Queued %s image(s) in %s localization job(s): %s", len(image_ids), len(job_ids), job_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
