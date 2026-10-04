#!/usr/bin/env python3
"""
Backfill shadow keypoints (eyes, beak, head top, shoulders) for the primary bird region (#426).

Per image: decode once (the localization decode) -> make sure a current display-space
``bird`` localization run exists for exactly these pixels (optionally running the shadow
detector with ``--localize-missing``) -> run the head pose model top-down on the rank-0
region -> write ``image_keypoint_runs`` + ``image_region_keypoints``.

Writes only the shadow localization/keypoint tables. Never touches ``images.bird_bbox``,
scores, keywords or phase status. Idempotent: a region that already has a final answer
from the same provider config is skipped (``--force`` re-runs it).

Candidates default to bird-tagged images whose legacy ``bird_bbox`` found a bird
(``--all-boxes`` drops the keyword gate).

``--selected-by <rule>`` (#492) instead targets images with an active production selection
(``image_localization_selections``) by that rule, and uses the *selected* region, which is
usually not on the current localization run. The selection's run must match the decoded
rendition; there is no re-localization in this mode.

Usage (gpu-shell container, project root):
  python scripts/backfill_region_keypoints.py --folder "/mnt/d/Photos/..." --localize-missing
  python scripts/backfill_region_keypoints.py --image-ids 101,102 --localize-missing
  python scripts/backfill_region_keypoints.py --limit 200 --localize-missing --dry-run
  python scripts/backfill_region_keypoints.py --selected-by "v1_regate_rule/3:a1c2e1f64b24cc79" --limit 20 --dry-run
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections import Counter

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_SQL_CANDIDATES = """
SELECT i.id, i.file_path
FROM images i
JOIN folders f ON i.folder_id = f.id
WHERE (i.bird_bbox ->> 'img_w') IS NOT NULL
  AND (? OR EXISTS (
    SELECT 1 FROM image_keywords ik
    JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
    WHERE ik.image_id = i.id AND kd.keyword_norm LIKE '%birds%'
  ))
  AND (? = '' OR f.path = ?)
ORDER BY f.path, i.id
"""

_SQL_PRIMARY_REGION = """
SELECT r.id AS run_id, r.rendition_hash, r.coord_space, g.id AS region_id,
       g.x1, g.y1, g.x2, g.y2
FROM image_localization_runs r
LEFT JOIN image_regions g ON g.localization_run_id = r.id AND g.rank = 0
WHERE r.image_id = ? AND r.detector_key = ? AND r.is_current
"""


_SQL_SELECTION_CANDIDATES = """
SELECT i.id, i.file_path
FROM image_localization_selections s
JOIN images i ON i.id = s.image_id
JOIN folders f ON i.folder_id = f.id
WHERE s.selected_by = ? AND s.detector_key = ? AND s.revoked_at IS NULL
  AND (? = '' OR f.path = ?)
ORDER BY f.path, i.id
"""

_SQL_SELECTED_REGION = """
SELECT r.id AS run_id, r.rendition_hash, r.coord_space, g.id AS region_id,
       g.x1, g.y1, g.x2, g.y2
FROM image_localization_selections s
JOIN image_localization_runs r ON r.id = s.localization_run_id
JOIN image_regions g ON g.id = s.region_id AND g.localization_run_id = r.id
WHERE s.image_id = ? AND s.detector_key = ? AND s.selected_by = ? AND s.revoked_at IS NULL
"""


def fetch_candidates(folder: str, image_ids: list[int], limit: int, all_boxes: bool = False,
                     selected_by: str = "") -> list[dict]:
    from modules import db
    from modules.localization import DETECTOR_KEY

    conn = db.get_connector()
    if image_ids:
        rows = []
        for iid in image_ids:
            row = conn.query_one("SELECT id, file_path FROM images WHERE id = ?", (iid,))
            if row:
                rows.append(row)
    elif selected_by:
        rows = conn.query(_SQL_SELECTION_CANDIDATES, (selected_by, DETECTOR_KEY, folder, folder))
    else:
        rows = conn.query(_SQL_CANDIDATES, (all_boxes, folder, folder))
    return rows[:limit] if limit > 0 else rows


def primary_region(image_id: int, selected_by: str = "") -> dict | None:
    """Rank-0 region of the current run, or the region actively selected by ``selected_by``."""
    from modules import db
    from modules.localization import DETECTOR_KEY

    conn = db.get_connector()
    if selected_by:
        return conn.query_one(_SQL_SELECTED_REGION, (int(image_id), DETECTOR_KEY, selected_by))
    return conn.query_one(_SQL_PRIMARY_REGION, (int(image_id), DETECTOR_KEY))


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--folder", default="", help="exact folders.path to restrict to")
    ap.add_argument("--image-ids", default="", help="comma-separated image ids (overrides --folder)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--all-boxes", action="store_true",
                    help="include legacy boxes on images without a birds* keyword")
    ap.add_argument("--localize-missing", action="store_true",
                    help="run the shadow bird detector when no current display-space run matches")
    ap.add_argument("--force", action="store_true", help="re-run regions that already have keypoints")
    ap.add_argument("--dry-run", action="store_true", help="infer but write nothing")
    ap.add_argument("--selected-by", default="",
                    help="use the region actively selected by this rule (image_localization_selections.selected_by)")
    a = ap.parse_args()
    selected_by = a.selected_by.strip()
    if selected_by and a.localize_missing:
        ap.error("--localize-missing cannot be combined with --selected-by (selected regions are never re-localized)")

    from modules.keypoints import (
        get_current_keypoint_run,
        infer_region_keypoints,
        is_unchanged,
        keypoints_config,
        load_keypoint_context,
        write_keypoint_run,
    )
    from modules.localization import (
        DecodeError,
        decode_for_localization,
        load_detector_context,
        localization_config,
        localize_image,
        max_regions_per_class,
    )
    from modules.rendition import COORD_SPACE_DISPLAY

    loc_cfg = localization_config()
    # Running this script is the opt-in; the config flag gates automatic use only.
    kp_cfg = {**loc_cfg, "keypoints": {"bird_head": {**keypoints_config(loc_cfg), "enabled": True}}}
    kctx = load_keypoint_context(kp_cfg)
    if kctx.load_error:
        logger.error("pose model unavailable: %s", kctx.load_error)
        return 2
    dctx = load_detector_context(loc_cfg) if a.localize_missing else None
    if dctx is not None and dctx.load_error:
        logger.error("bird detector unavailable: %s", dctx.load_error)
        return 2

    ids = [int(x) for x in a.image_ids.split(",") if x.strip()]
    rows = fetch_candidates(a.folder.strip(), ids, a.limit, a.all_boxes, selected_by)
    logger.info("candidates: %d (provider %s, config %s)", len(rows), kctx.version, kctx.config_hash)

    counts: Counter = Counter()
    t0 = time.time()
    for n, row in enumerate(rows, 1):
        if n % 100 == 0:
            logger.info("%d/%d %.0fs %s", n, len(rows), time.time() - t0, dict(counts))
        image_id, path = int(row["id"]), row.get("file_path") or ""
        if not path or not os.path.exists(path):
            counts["file_missing"] += 1
            continue
        # Cheap resume: a region that already has this provider's answer is skipped without
        # decoding (its localization run was matched to the rendition when it was written).
        cur = primary_region(image_id, selected_by)
        if selected_by and cur is None:
            counts["no_selection"] += 1
            continue
        if (not a.force and cur and cur.get("region_id") is not None
                and cur.get("coord_space") == COORD_SPACE_DISPLAY
                and is_unchanged(get_current_keypoint_run(int(cur["region_id"])), kctx.config_hash)):
            counts["unchanged"] += 1
            continue
        try:
            decoded = decode_for_localization(path)
        except DecodeError:
            counts["decode_error"] += 1
            continue
        want_hash = decoded.descriptor.rendition_hash

        cur = primary_region(image_id, selected_by)
        matches = bool(cur) and cur.get("coord_space") == COORD_SPACE_DISPLAY \
            and cur.get("rendition_hash") == want_hash
        if not matches:
            if selected_by:
                counts["selection_rendition_mismatch"] += 1
                continue
            if dctx is None or a.dry_run:
                counts["no_matching_localization"] += 1
                continue
            localize_image(image_id, path, dctx, max_regions=max_regions_per_class(loc_cfg),
                           decoded=decoded)
            cur = primary_region(image_id)
            if not cur or cur.get("rendition_hash") != want_hash:
                counts["localization_failed"] += 1
                continue
        if cur.get("region_id") is None:
            counts["no_region"] += 1
            continue

        region_id = int(cur["region_id"])
        if not a.force and is_unchanged(get_current_keypoint_run(region_id), kctx.config_hash):
            counts["unchanged"] += 1
            continue
        region = (float(cur["x1"]), float(cur["y1"]), float(cur["x2"]), float(cur["y2"]))
        outcome = infer_region_keypoints(kctx, decoded.image, region)
        counts[outcome["status"]] += 1
        if outcome["status"] == "detected":
            counts["visible_eye"] += any(k["visible"] for k in outcome["keypoints"] if k["name"].endswith("_eye"))
        if not a.dry_run:
            write_keypoint_run(region_id, kctx, outcome)

    logger.info("done in %.0fs: %s", time.time() - t0, dict(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
