#!/usr/bin/env python3
"""Promote owner-validated regions to production through localization selections (#484, #472 step 6).

Input is a frozen manifest (JSON) written by a research harness, e.g.
``v1_regate.py promotion-manifest`` for #472:

    {"schema_version": 1, "selected_by": "v1_regate_rule/3:<hash>",
     "detector_version": "v1_regate_rule/3", "detector_config_hash": "<hash>",
     "evidence": {...}, "rows": [{"image_id", "v1_run_id", "rendition_hash",
                                 "region": [x1, y1, x2, y2], "conf", "source", "stratum"}]}

For each row, ``apply`` persists the region as an unpublished localization run (the v1 shadow
run stays current) and selects it, which projects ``images.bird_bbox``. Rows are skipped unless
``bird_bbox`` still holds the exact no-bird placeholder and the v1 run they were drawn from is
still current with the same rendition. ``revoke`` revokes this manifest's selections and
restores the replaced ``bird_bbox`` values. Take a database backup before ``apply``.

In gpu-shell, from /app:
  python scripts/maintenance/promote_localization_selections.py dry-run --manifest <path>
  python scripts/maintenance/promote_localization_selections.py apply --manifest <path> --confirm
  python scripts/maintenance/promote_localization_selections.py revoke --manifest <path> --confirm
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

SENTINEL = {"detected": False}
DETECTOR_KEY = "bird"
COCO_BIRD_CLASS_ID = "14"

_STATE_SQL = """
    SELECT i.bird_bbox, r.id AS run_id, r.is_current, r.rendition_hash, r.rendition_version,
           r.source_hash, r.source_hash_version, r.orientation, r.display_width, r.display_height
    FROM images i
    LEFT JOIN image_localization_runs r ON r.id = ?
    WHERE i.id = ?
"""
_PROMOTED_RUN_SQL = """
    SELECT r.id AS run_id, g.id AS region_id
    FROM image_localization_runs r
    JOIN image_regions g ON g.localization_run_id = r.id AND g.rank = 0
    WHERE r.image_id = ? AND r.detector_key = ? AND r.detector_version = ? AND r.detector_config_hash = ?
    ORDER BY r.id DESC LIMIT 1
"""


def load_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unexpected manifest schema_version")
    for key in ("selected_by", "detector_version", "detector_config_hash", "rows"):
        if not payload.get(key):
            raise ValueError(f"manifest is missing {key!r}")
    ids = [int(row["image_id"]) for row in payload["rows"]]
    if len(ids) != len(set(ids)):
        raise ValueError("manifest contains duplicate image IDs")
    return payload


def _json(value):
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def row_state(state: dict | None, active: dict | None, row: dict, selected_by: str) -> str:
    """Classify one manifest row against the live database before any write."""
    if state is None:
        return "missing_image"
    if active is not None:
        return "already_selected" if active.get("selected_by") == selected_by else "other_selection_active"
    if _json(state.get("bird_bbox")) != SENTINEL:
        return "production_changed"
    if state.get("run_id") is None or not state.get("is_current"):
        return "v1_run_not_current"
    if state.get("rendition_hash") != row["rendition_hash"]:
        return "rendition_changed"
    if not state.get("display_width") or not state.get("display_height"):
        return "no_dimensions"
    return "ready"


def _states(manifest: dict):
    from modules import db
    from modules.localization_selection import active_selection

    conn = db.get_connector()
    for row in manifest["rows"]:
        iid = int(row["image_id"])
        state = conn.query_one(_STATE_SQL, (int(row["v1_run_id"]), iid))
        yield row, state, row_state(state, active_selection(iid, DETECTOR_KEY), row, manifest["selected_by"])


def dry_run(manifest: dict) -> Counter:
    counts: Counter = Counter()
    for row, _, st in _states(manifest):
        counts[st] += 1
        counts[f"{row.get('stratum', '?')}:{st}"] += 1
    return counts


def _persist_run(manifest: dict, row: dict, state: dict) -> int:
    """Store the validated region as an unpublished run; reuse it on a re-run of ``apply``."""
    from modules import db
    from modules.localization import write_run

    iid = int(row["image_id"])
    existing = db.get_connector().query_one(
        _PROMOTED_RUN_SQL, (iid, DETECTOR_KEY, manifest["detector_version"], manifest["detector_config_hash"]))
    if existing:
        return int(existing["region_id"])
    run = {
        "image_id": iid, "job_id": None, "detector_key": DETECTOR_KEY,
        "detector_version": manifest["detector_version"],
        "detector_config_hash": manifest["detector_config_hash"],
        "source_hash": state.get("source_hash"), "source_hash_version": state.get("source_hash_version"),
        "rendition_hash": state["rendition_hash"], "rendition_version": state.get("rendition_version"),
        "coord_space": "display_normalized", "orientation": state.get("orientation"),
        "display_width": state["display_width"], "display_height": state["display_height"],
        "status": "detected", "is_retryable": False, "is_current": False,
    }
    region = {"conf": float(row["conf"]), "rank": 0, "region": tuple(row["region"]),
              "object_class": "bird", "provider_class_id": COCO_BIRD_CLASS_ID}
    write_run(run, [region], publish=False)
    return int(db.get_connector().query_one(
        _PROMOTED_RUN_SQL, (iid, DETECTOR_KEY, manifest["detector_version"],
                            manifest["detector_config_hash"]))["region_id"])


def apply(manifest: dict) -> Counter:
    from modules.localization_selection import select_region

    counts: Counter = Counter()
    for row, state, st in _states(manifest):
        if st != "ready":
            counts[f"skipped:{st}"] += 1
            continue
        region_id = _persist_run(manifest, row, state)
        evidence = {**(manifest.get("evidence") or {}), "stratum": row.get("stratum"), "source": row.get("source")}
        res = select_region(int(row["image_id"]), region_id, manifest["selected_by"], evidence,
                            detector_key=DETECTOR_KEY, expect_bird_bbox=SENTINEL)
        counts["selected" if res["status"] == "selected" else f"skipped:{res['status']}"] += 1
    return counts


def revoke(manifest: dict, reason: str) -> Counter:
    from modules.localization_selection import active_selection, revoke_selection

    counts: Counter = Counter()
    for row in manifest["rows"]:
        iid = int(row["image_id"])
        active = active_selection(iid, DETECTOR_KEY)
        if active is None or active.get("selected_by") != manifest["selected_by"]:
            counts["not_ours"] += 1
            continue
        counts[revoke_selection(iid, reason, detector_key=DETECTOR_KEY)["status"]] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=("dry-run", "apply", "revoke"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--confirm", action="store_true", help="required for apply / revoke")
    parser.add_argument("--reason", default="manual revoke")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.action in ("apply", "revoke") and not args.confirm:
        parser.error(f"{args.action} changes images.bird_bbox; pass --confirm")
    manifest = load_manifest(args.manifest)
    if args.action == "dry-run":
        result = dry_run(manifest)
    elif args.action == "apply":
        result = apply(manifest)
    else:
        result = revoke(manifest, args.reason)
    print(json.dumps(dict(sorted(result.items())), indent=1))


if __name__ == "__main__":
    main()
