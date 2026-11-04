#!/usr/bin/env python3
"""
Backfill shadow ``bird_agreement`` runs: does RTMDet confirm each bird region? (spec 08, #780).

Per image: read the current ``bird`` run, decode once, run RTMDet on each padded region crop, write one
``bird_agreement`` run, unpublished so that no consumer sees it. Writes only
``image_localization_runs`` and ``image_regions`` rows under that detector key. Needs ``localization.agreement.enabled``. A region already scored for the same
identity is skipped (``--force`` re-runs it). Print the per-shoot table with ``--report``.

Usage (gpu-shell container, project root):
  python scripts/backfill_bird_agreement.py --folder "/mnt/d/Photos/..." --limit 200 --dry-run
  python scripts/backfill_bird_agreement.py --image-ids 101,102
  python scripts/backfill_bird_agreement.py --report --folder "/mnt/d/Photos/..."
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_SQL_CANDIDATES = """
SELECT i.id, i.file_path
FROM image_localization_runs r
JOIN images i ON i.id = r.image_id
JOIN folders f ON i.folder_id = f.id
WHERE r.detector_key = 'bird' AND r.is_current AND r.status = 'detected'
  AND (? = '' OR f.path = ?)
ORDER BY f.path, i.id
"""

_SQL_BY_ID = "SELECT id, file_path FROM images WHERE id = ?"

_SQL_REPORT = """
SELECT f.path AS shoot, g.confidence AS score, COALESCE(e.eyes, 0) AS eyes
FROM image_localization_runs r
JOIN image_regions g ON g.localization_run_id = r.id
JOIN images i ON i.id = r.image_id
JOIN folders f ON i.folder_id = f.id
LEFT JOIN (
    SELECT kr.region_id, COUNT(*) AS eyes
    FROM image_keypoint_runs kr
    JOIN image_region_keypoints k ON k.keypoint_run_id = kr.id
    WHERE kr.is_current AND kr.status = 'detected' AND k.visible AND k.confidence >= ?
      AND k.name IN ('left_eye', 'right_eye')
    GROUP BY kr.region_id
) e ON e.region_id = CAST(split_part(g.provider_class_id, ':', 3) AS BIGINT)
WHERE r.detector_key = 'bird_agreement' AND r.status = 'detected'
  AND r.id = (SELECT MAX(x.id) FROM image_localization_runs x
              WHERE x.image_id = r.image_id AND x.detector_key = 'bird_agreement')
  AND (? = '' OR f.path = ?)
ORDER BY f.path
"""


def fetch_candidates(folder: str, image_ids: list[int], limit: int) -> list[dict]:
    from modules import db

    conn = db.get_connector()
    if image_ids:
        rows = [conn.query_one(_SQL_BY_ID, (i,)) for i in image_ids]
        return [r for r in rows if r]
    rows = conn.query(_SQL_CANDIDATES, (folder, folder)) or []
    return rows[:limit] if limit else rows


def report(folder: str, limit: float) -> int:
    from modules import db
    from modules.keypoints import EYE_CONSUMER_MIN_CONF
    from modules.localization_agreement_runner import summarize_shoots

    rows = db.get_connector().query(_SQL_REPORT, (EYE_CONSUMER_MIN_CONF, folder, folder)) or []
    print("shoot\tregions\tat_or_above\tbelow\teyes\teyes_below")
    for shoot, s in sorted(summarize_shoots(rows, limit).items()):
        print(f"{shoot}\t{s['regions']}\t{s['at_or_above']}\t{s['below']}\t{s['eyes']}\t{s['eyes_below']}")
    return 0


def main() -> int:
    from modules.localization_agreement import AGREEMENT_LIMIT

    ap = argparse.ArgumentParser(description="Shadow bird box agreement backfill (spec 08)")
    ap.add_argument("--folder", default="", help="exact folders.path to restrict to")
    ap.add_argument("--image-ids", default="", help="comma-separated image ids (overrides --folder)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="re-run images that already have a current run")
    ap.add_argument("--dry-run", action="store_true", help="score but write nothing")
    ap.add_argument("--report", action="store_true", help="print the per-shoot table and exit")
    ap.add_argument("--agreement-limit", type=float, default=AGREEMENT_LIMIT, help="report only")
    a = ap.parse_args()

    if a.report:
        return report(a.folder, a.agreement_limit)

    from modules.localization import localization_config
    from modules.localization_agreement_runner import load_agreement_context, score_image

    actx = load_agreement_context(localization_config())
    if actx is None:
        logger.error("localization.agreement.enabled is false")
        return 2
    if not actx.rtmdet.enabled:
        logger.error("RTMDet unavailable: %s", actx.rtmdet.error_code)
        return 2

    ids = [int(x) for x in a.image_ids.split(",") if x.strip()]
    counts: Counter = Counter()
    for row in fetch_candidates(a.folder, ids, a.limit):
        status = score_image(row["id"], row["file_path"], actx, force=a.force, dry_run=a.dry_run)
        counts[status or "skipped"] += 1
    logger.info("done%s: %s", " (dry run)" if a.dry_run else "", dict(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
