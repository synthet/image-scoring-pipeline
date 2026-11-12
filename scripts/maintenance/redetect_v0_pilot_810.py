#!/usr/bin/env python3
"""#810 pilot: re-detect a frozen, seeded sample of current bird_detect_v0 runs with bird_detect_v1.

Three modes, run in gpu-shell from /app:

  # 1. Freeze the sample (read-only). Candidate image ids come from a file, one id per line.
  python scripts/maintenance/redetect_v0_pilot_810.py snapshot --image-ids-file ids.txt \
      --manifest .agent/scratch/pilot-810/manifest.json --seed 810 --size 200

  # 2. Re-detect (writes versioned localization runs only). Resumable: frames already in
  #    the results file are skipped.
  python scripts/maintenance/redetect_v0_pilot_810.py apply \
      --manifest .agent/scratch/pilot-810/manifest.json --results .agent/scratch/pilot-810/results.jsonl --limit 10

  # 3. Print rollback SQL (no DB writes): make each frame's v0 run current again.
  python scripts/maintenance/redetect_v0_pilot_810.py rollback-sql \
      --manifest .agent/scratch/pilot-810/manifest.json --results .agent/scratch/pilot-810/results.jsonl

What ``apply`` writes: ``localize_routed`` adds a new current ``bird`` run and its regions,
demotes the v0 run (kept, ``is_current = false``) and may upsert a scene label. It writes no
selection, species, ``bird_bbox`` or phase status. A scene-route skip writes a current
``disabled`` run; it is recorded as ``status = disabled`` and counted as "v1 skipped".
File formats: ``pilot-810/1`` on GitHub issue #810.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

SCHEMA = "pilot-810/1"
V0_VERSION = "synthet/bird-detect-v0/bird_detect_v0.pt"
V1_VERSION = "synthet/bird-detect-v0/bird_detect_v1.pt"
V1_SHA256 = "6d09339fb3286c8d10395c29e3b0c14da92d86be5c9d4753c38d4a2ef2e447ba"
STRATA = ("small", "medium", "large")

_CANDIDATE_SQL = """
SELECT i.id AS image_id, i.file_path, f.path AS shoot,
       r.id AS run_id, r.detector_version, r.detector_config_hash, r.status,
       (r.legacy_payload IS NOT NULL) AS has_legacy_payload,
       r.display_width, r.display_height,
       g.id AS region_id, g.x1, g.y1, g.x2, g.y2, g.confidence
FROM images i
LEFT JOIN folders f ON f.id = i.folder_id
JOIN image_localization_runs r ON r.image_id = i.id AND r.detector_key = 'bird' AND r.is_current
LEFT JOIN image_regions g ON g.localization_run_id = r.id AND g.rank = 0
WHERE i.id = ?
"""
_CURRENT_SQL = """
SELECT r.id AS run_id, r.status, r.detector_version, r.error_code, r.error_detail,
       r.display_width, r.display_height,
       g.id AS region_id, g.x1, g.y1, g.x2, g.y2, g.confidence
FROM image_localization_runs r
LEFT JOIN image_regions g ON g.localization_run_id = r.id AND g.rank = 0
WHERE r.image_id = ? AND r.detector_key = 'bird' AND r.is_current
"""


# --------------------------------------------------------------------------- pure helpers

def eligibility(row: dict | None) -> str:
    """Why a candidate image can or cannot enter the pool."""
    if row is None:
        return "no_current_bird_run"
    if row.get("detector_version") != V0_VERSION:
        return "current_run_not_v0"
    if row.get("status") != "detected" or row.get("region_id") is None:
        return "v0_not_detected"
    if row.get("has_legacy_payload"):
        # image_bird_bbox_compat reads the current run's legacy_payload; demoting it would
        # change what compat readers get, so these stay out of the pilot.
        return "has_legacy_payload"
    return "eligible"


def box_area(box) -> float:
    x1, y1, x2, y2 = box
    return max(0.0, float(x2) - float(x1)) * max(0.0, float(y2) - float(y1))


def tercile_cuts(areas) -> tuple[float, float]:
    """Area cut points splitting the pool into three equal-count strata."""
    ordered = sorted(areas)
    if len(ordered) < 3:
        raise ValueError("need at least 3 eligible frames to form terciles")
    n = len(ordered)
    return ordered[n // 3], ordered[(2 * n) // 3]


def stratum_for(area: float, cuts: tuple[float, float]) -> str:
    if area < cuts[0]:
        return "small"
    if area < cuts[1]:
        return "medium"
    return "large"


def draw_stratified(pool: list[dict], *, seed: int, size: int) -> list[dict]:
    """Seeded draw of ``size`` frames split as evenly as possible over the three strata."""
    rng = random.Random(seed)
    by = {s: sorted((f for f in pool if f["stratum"] == s), key=lambda f: f["image_id"]) for s in STRATA}
    quota = {s: size // 3 for s in STRATA}
    for s in STRATA[: size % 3]:
        quota[s] += 1
    picked = []
    for s in STRATA:
        if len(by[s]) < quota[s]:
            raise ValueError(f"stratum {s} has {len(by[s])} frames, needs {quota[s]}")
        picked += rng.sample(by[s], quota[s])
    return sorted(picked, key=lambda f: f["image_id"])


def result_record(image_id: int, row: dict | None, seconds: float) -> dict:
    """One ``results.jsonl`` line from the image's current bird run after re-detection."""
    row = row or {}
    status = row.get("status") or "missing"
    v1 = {
        "run_id": row.get("run_id"),
        "status": status,
        "detector_version": row.get("detector_version"),
        "skip_reason": None,
        "region_id": None,
        "box": None,
        "confidence": None,
        "display_width": row.get("display_width"),
        "display_height": row.get("display_height"),
    }
    if status == "detected" and row.get("region_id") is not None:
        v1["region_id"] = row["region_id"]
        v1["box"] = [row["x1"], row["y1"], row["x2"], row["y2"]]
        v1["confidence"] = row.get("confidence")
    elif status != "detected":
        v1["skip_reason"] = row.get("error_code") or row.get("error_detail")
    return {"image_id": int(image_id), "v1": v1, "seconds": round(float(seconds), 3)}


def rollback_statements(manifest: dict, results: list[dict]) -> list[str]:
    """SQL that makes each frame's frozen v0 run current again (new run demoted, not deleted)."""
    v0_by_image = {int(f["image_id"]): int(f["v0"]["run_id"]) for f in manifest["frames"]}
    out = []
    for r in results:
        image_id = int(r["image_id"])
        v0_run = v0_by_image.get(image_id)
        new_run = (r.get("v1") or {}).get("run_id")
        if v0_run is None or new_run is None or int(new_run) == v0_run:
            continue
        out.append(
            "UPDATE image_localization_runs SET is_current = FALSE "
            f"WHERE id = {int(new_run)} AND image_id = {image_id};"
        )
        out.append(
            "UPDATE image_localization_runs SET is_current = TRUE "
            f"WHERE id = {v0_run} AND image_id = {image_id};"
        )
    return out


# --------------------------------------------------------------------------- DB-backed modes

def snapshot(ids_file: Path, manifest_path: Path, *, seed: int, size: int) -> dict:
    from modules import db

    if manifest_path.exists():
        raise FileExistsError(f"manifest already exists: {manifest_path}")
    ids = sorted({int(x) for x in ids_file.read_text(encoding="utf-8").split() if x.strip()})
    conn = db.get_connector()
    reasons: Counter = Counter()
    pool = []
    for image_id in ids:
        row = conn.query_one(_CANDIDATE_SQL, (image_id,))
        reason = eligibility(row)
        reasons[reason] += 1
        if reason != "eligible":
            continue
        box = [row["x1"], row["y1"], row["x2"], row["y2"]]
        pool.append({
            "image_id": image_id,
            "file_path": row["file_path"],
            "shoot": row["shoot"],
            "area": box_area(box),
            "v0": {
                "run_id": int(row["run_id"]),
                "region_id": int(row["region_id"]),
                "detector_version": row["detector_version"],
                "detector_config_hash": row["detector_config_hash"],
                "box": box,
                "confidence": row["confidence"],
                "display_width": row["display_width"],
                "display_height": row["display_height"],
            },
        })
    cuts = tercile_cuts([f["area"] for f in pool])
    for f in pool:
        f["stratum"] = stratum_for(f["area"], cuts)
    frames = draw_stratified(pool, seed=seed, size=size)
    manifest = {
        "schema": SCHEMA,
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": seed,
        "size": size,
        "candidate_ids": len(ids),
        "eligibility": dict(reasons),
        "pool_by_stratum": dict(Counter(f["stratum"] for f in pool)),
        "shoots": sorted({f["shoot"] for f in frames if f["shoot"]}),
        "v1_detector": {"detector_key": "bird", "detector_version": V1_VERSION, "weights_sha256": V1_SHA256},
        "tercile_cuts": {"area_frac": list(cuts)},
        "frames": [{k: v for k, v in f.items() if k != "area"} for f in frames],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("x", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
        fh.write("\n")
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    log.info("Frozen %d frames (pool %d, %s) in %s sha256=%s",
             len(frames), len(pool), dict(reasons), manifest_path, digest)
    return manifest


def _load_results(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def apply(manifest_path: Path, results_path: Path, *, limit: int) -> Counter:
    from modules import db
    from modules.localization import (
        load_detector_context,
        localization_config,
        max_regions_per_class,
        weights_sha256,
    )
    from modules.localization_runner import localize_routed, scene_router_or_none

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise ValueError(f"unexpected manifest schema: {manifest.get('schema')}")
    cfg = localization_config()
    ctx = load_detector_context(cfg)
    if not ctx.enabled or ctx.load_error or ctx.detector is None:
        raise RuntimeError(f"bird detector unavailable: {ctx.load_error or 'disabled'}")
    if ctx.version != V1_VERSION:
        raise RuntimeError(f"expected {V1_VERSION}, got {ctx.version}")
    actual = weights_sha256(ctx.detector._resolve_weights_path())
    if actual != V1_SHA256:
        raise RuntimeError(f"v1 weights hash mismatch: {actual}")

    done = {int(r["image_id"]) for r in _load_results(results_path)}
    conn = db.get_connector()
    router = scene_router_or_none()
    max_regions = max_regions_per_class(cfg)
    counts: Counter = Counter()
    todo = [f for f in manifest["frames"] if int(f["image_id"]) not in done]
    if limit > 0:
        todo = todo[:limit]
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with results_path.open("a", encoding="utf-8") as out:
        for n, frame in enumerate(todo, 1):
            image_id = int(frame["image_id"])
            current = conn.query_one(_CURRENT_SQL, (image_id,))
            if not current or int(current["run_id"]) != int(frame["v0"]["run_id"]):
                counts["v0_no_longer_current"] += 1
                log.warning("image %s: frozen v0 run is no longer current; skipped", image_id)
                continue
            t0 = time.monotonic()
            localize_routed(router, image_id, frame["file_path"] or "", ctx, max_regions=max_regions)
            seconds = time.monotonic() - t0
            record = result_record(image_id, conn.query_one(_CURRENT_SQL, (image_id,)), seconds)
            out.write(json.dumps(record) + "\n")
            out.flush()
            counts[record["v1"]["status"]] += 1
            if n % 10 == 0 or n == len(todo):
                log.info("%d/%d %s", n, len(todo), dict(counts))
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("snapshot", help="freeze the seeded sample (read-only)")
    s.add_argument("--image-ids-file", type=Path, required=True)
    s.add_argument("--manifest", type=Path, required=True)
    s.add_argument("--seed", type=int, default=810)
    s.add_argument("--size", type=int, default=200)
    a = sub.add_parser("apply", help="re-detect the frozen frames with v1")
    a.add_argument("--manifest", type=Path, required=True)
    a.add_argument("--results", type=Path, required=True)
    a.add_argument("--limit", type=int, default=0, help="process the next N unfinished frames (0 = all)")
    r = sub.add_parser("rollback-sql", help="print SQL restoring the v0 runs (no DB writes)")
    r.add_argument("--manifest", type=Path, required=True)
    r.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.mode == "snapshot":
        snapshot(args.image_ids_file, args.manifest, seed=args.seed, size=args.size)
    elif args.mode == "apply":
        if args.limit < 0:
            parser.error("--limit must be nonnegative")
        log.info("Re-detect: %s", dict(apply(args.manifest, args.results, limit=args.limit)))
    else:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        print("BEGIN;")
        for stmt in rollback_statements(manifest, _load_results(args.results)):
            print(stmt)
        print("COMMIT;")
    return 0


if __name__ == "__main__":
    sys.exit(main())
