#!/usr/bin/env python3
"""Rescan a frozen set of legacy no-bird results with bird_detect_v1 in shadow.

Only image_localization_runs/image_regions are written. In particular, this does not
change images.bird_bbox or image_phase_status. A legacy detection is not proof that
v0 produced it: the import did not record weights. Review new boxes before promotion.

In gpu-shell, from /app:
  python scripts/maintenance/shadow_rescan_bird_v1_misses.py --manifest .agent/scratch/bird_v1_misses.json --snapshot
  python scripts/maintenance/shadow_rescan_bird_v1_misses.py --manifest .agent/scratch/bird_v1_misses.json --apply --limit 100
  python scripts/maintenance/shadow_rescan_bird_v1_misses.py --manifest .agent/scratch/bird_v1_misses.json --apply
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from modules.localization import (  # noqa: E402
    load_detector_context,
    localization_config,
    localize_image,
    max_regions_per_class,
    weights_sha256,
)

log = logging.getLogger(__name__)
EXPECTED_SHA256 = "6d09339fb3286c8d10395c29e3b0c14da92d86be5c9d4753c38d4a2ef2e447ba"
_SENTINEL = {"detected": False}

_CANDIDATES_SQL = """
SELECT i.id AS image_id, r.id AS legacy_run_id
FROM images i
JOIN image_localization_runs r ON r.image_id = i.id
WHERE i.bird_bbox = '{"detected": false}'::jsonb
  AND r.detector_key = 'bird' AND r.is_current
  AND r.detector_version = 'legacy_unversioned' AND r.status = 'no_detection'
ORDER BY i.id
"""
_STATE_SQL = """
SELECT i.file_path, i.bird_bbox, r.id AS run_id, r.status,
       r.detector_version, r.detector_config_hash
FROM images i
LEFT JOIN image_localization_runs r
  ON r.image_id = i.id AND r.detector_key = 'bird' AND r.is_current
WHERE i.id = ?
"""


def _bbox(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def candidate_state(row: dict | None, legacy_run_id: int, config_hash: str) -> str:
    """Classify an image against its frozen imported run before any write."""
    if row is None:
        return "missing"
    if (row.get("detector_version") == "synthet/bird-detect-v0/bird_detect_v1.pt"
            and row.get("detector_config_hash") == config_hash):
        return "already_v1"
    if _bbox(row.get("bird_bbox")) != _SENTINEL:
        return "production_changed"
    if (row.get("run_id") != legacy_run_id
            or row.get("detector_version") != "legacy_unversioned"
            or row.get("status") != "no_detection"):
        return "shadow_changed"
    return "ready"


def snapshot(path: Path) -> int:
    """Freeze exact image/run ID pairs so later imports cannot expand the cohort."""
    from modules import db

    if path.exists():
        raise FileExistsError(f"manifest already exists: {path}")
    rows = db.get_connector().query(_CANDIDATES_SQL)
    payload = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": "current legacy_unversioned no_detection with exact production sentinel",
        "expected_sha256": EXPECTED_SHA256,
        "rows": [[int(r["image_id"]), int(r["legacy_run_id"])] for r in rows],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
        fh.write("\n")
    log.info("Frozen %d candidate image/run pairs in %s", len(rows), path)
    return len(rows)


def run(path: Path, limit: int) -> Counter:
    """Write only versioned shadow runs for unchanged members of the snapshot."""
    from modules import db

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("expected_sha256") != EXPECTED_SHA256:
        raise ValueError("manifest schema or pinned v1 weights hash does not match")
    pairs = payload["rows"]
    if len(pairs) != len({int(pair[0]) for pair in pairs}):
        raise ValueError("manifest contains duplicate image IDs")

    cfg = localization_config()
    ctx = load_detector_context(cfg)
    if not ctx.enabled or ctx.load_error or ctx.detector is None:
        raise RuntimeError(f"bird detector unavailable: {ctx.load_error or 'disabled'}")
    if ctx.version != "synthet/bird-detect-v0/bird_detect_v1.pt":
        raise RuntimeError(f"expected bird_detect_v1.pt, got {ctx.version}")
    actual_hash = weights_sha256(ctx.detector._resolve_weights_path())
    if actual_hash != EXPECTED_SHA256:
        raise RuntimeError(f"v1 weights hash mismatch: {actual_hash}")

    conn = db.get_connector()
    counts: Counter = Counter()
    max_regions = max_regions_per_class(cfg)
    selected = pairs[:limit] if limit > 0 else pairs
    for n, (image_id, legacy_run_id) in enumerate(selected, 1):
        row = conn.query_one(_STATE_SQL, (int(image_id),))
        state = candidate_state(row, int(legacy_run_id), ctx.config_hash)
        if state != "ready":
            counts[state] += 1
            continue
        outcome = localize_image(int(image_id), row["file_path"] or "", ctx, max_regions=max_regions)
        counts[outcome.status] += 1
        if outcome.unchanged:
            counts["unchanged"] += 1
        if n % 100 == 0 or n == len(selected):
            log.info("%d/%d %s", n, len(selected), dict(counts))
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--snapshot", action="store_true", help="freeze candidate IDs, no DB writes")
    action.add_argument("--apply", action="store_true", help="write shadow localization runs")
    parser.add_argument("--limit", type=int, default=0, help="process first N snapshot rows (0 = all)")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.snapshot:
        snapshot(args.manifest)
    else:
        log.info("Shadow rescan: %s", dict(run(args.manifest, args.limit)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
