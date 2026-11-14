#!/usr/bin/env python3
"""#858 species parity: classify the same images through two BioCLIP input arms and compare them.

The two production paths look alike for species: localization and BioCLIP's embedded detector build
``BirdDetector`` from the same ``bird_detection`` config. This study checks that claim without labels. It also
covers decision B on #810: v1 against v0 boxes for species.

An arm is either ``embedded`` (``classify(use_detector=True)``, the embedded detector picks the box) or
``region:<field>`` (``classify(region=frame[<field>])``, a padded crop of a stored box; the embedded detector does
not run). Both arms use the same model, species list and inference path as ``BirdSpeciesRunner``.

``region:box`` is the counterfactual input after the frame's current run is **promoted to a selection**. Today an
unselected current run is a shadow result: species reads only selections (``species_input_for_image``), and the
retired-detector path (``stored_box_input`` → ``read_bird_bbox``) also ignores native current runs without a
selection. So v0 against v1 matters to species only through promotion; ``by_detector_version`` splits the result.
The report also compares the stored outcome at ``bird_species.min_confidence`` (abstentions included), which is
what species persists, and flags frames whose decoded aspect differs from the run's display aspect.

Three modes; run ``sample`` and ``run`` in gpu-shell from /app:

  # 1. Freeze a seeded sample of the #694 cohort (read-only): bird-tagged images whose current ``bird`` run is
  #    detected with no active selection, minus the 390-frame #694 owner sample.
  python scripts/research/species_parity_858.py sample --out S.jsonl --seed 858 --size 200 \
      --exclude-manifest .agent/scratch/promotion-694/owner-sample-manifest-20261109.json

  # 2. Classify every frame through both arms (GPU; no DB writes). Resumable.
  python scripts/research/species_parity_858.py run --sample S.jsonl --arm-a region:box --arm-b embedded --out R.jsonl

  # 3. Compare (pure).
  python scripts/research/species_parity_858.py report --results R.jsonl --out report.json

The parity threshold is the owner's to set before a run (#858); ``report`` states counts, agreement and its
Wilson interval, and gives no verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SCHEMA = "species-parity-858/1"
DIFFERENT_BOX_IOU = 0.5
ASPECT_TOL = 0.02  # same tolerance as the skills pilot_eval display_mismatch

_COHORT_SQL = """
WITH bird AS (
  SELECT DISTINCT ik.image_id FROM image_keywords ik
  JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
  WHERE kd.keyword_norm LIKE 'bird%'
)
SELECT r.image_id, r.id AS run_id, r.detector_version, r.display_width, r.display_height,
       g.id AS region_id, g.confidence,
       g.x1, g.y1, g.x2, g.y2, i.file_path
FROM image_localization_runs r
JOIN bird b ON b.image_id = r.image_id
JOIN images i ON i.id = r.image_id
JOIN image_regions g ON g.localization_run_id = r.id AND g.rank = 0
WHERE r.detector_key = 'bird' AND r.is_current AND r.status = 'detected'
  AND r.coord_space = 'display_normalized'
  AND NOT EXISTS (SELECT 1 FROM image_localization_selections s
                  WHERE s.image_id = r.image_id AND s.detector_key = 'bird' AND s.revoked_at IS NULL)
ORDER BY r.image_id
"""


# --------------------------------------------------------------------------- pure helpers (tested)

def box_iou(a, b) -> float | None:
    """IoU of two normalized ``[x1, y1, x2, y2]`` boxes; ``None`` when either is missing."""
    if a is None or b is None:
        return None
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def box_area(box) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for k successes out of n."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def normalized_pixel_box(bbox: dict | None) -> list[float] | None:
    """The embedded detector's ``last_bbox`` (pixels plus ``img_w``/``img_h``) as a normalized box."""
    if not bbox or not bbox.get("img_w") or not bbox.get("img_h") or "x1" not in bbox:
        return None
    w, h = float(bbox["img_w"]), float(bbox["img_h"])
    return [bbox["x1"] / w, bbox["y1"] / h, bbox["x2"] / w, bbox["y2"] / h]


def area_bands(areas) -> tuple[float, float]:
    """Tercile cut points of the sample's box areas."""
    ordered = sorted(areas)
    if len(ordered) < 3:
        raise ValueError("need at least 3 frames to form area bands")
    n = len(ordered)
    return ordered[n // 3], ordered[(2 * n) // 3]


def band_for(area: float, cuts: tuple[float, float]) -> str:
    return "small" if area < cuts[0] else "medium" if area < cuts[1] else "large"


def aspect_mismatch(size, display) -> bool | None:
    """True when the image species decodes does not have the stored run's display aspect (boxes would shift)."""
    if not size or not display or not all(display):
        return None
    a, d = size[0] / size[1], display[0] / display[1]
    return abs(a - d) > ASPECT_TOL * d


def stored_outcome(arm: dict, min_conf: float) -> str:
    """What ``bird_species`` would persist: the top-1 name at or above ``min_conf``, else an abstention."""
    return arm["top1"] if arm["conf"] >= min_conf else "<abstain>"


def _ok(arm: dict | None) -> bool:
    return bool(arm) and not arm.get("error") and arm.get("top1") is not None


def compare(rows: list[dict], *, by_version: bool = True) -> dict:
    """Counts for one results file: each row has ``arms.a`` / ``arms.b`` with ``top1``, ``conf`` and ``box``.

    Pairs where either arm failed are counted, not compared. No verdict: the parity threshold is the owner's.
    """
    pairs = [r for r in rows if _ok(r["arms"]["a"]) and _ok(r["arms"]["b"])]
    agree = [r for r in pairs if r["arms"]["a"]["top1"] == r["arms"]["b"]["top1"]]
    ious = [box_iou(r["arms"]["a"].get("box"), r["arms"]["b"].get("box")) for r in pairs]
    with_both_boxes = [v for v in ious if v is not None]
    areas = [r["area"] for r in pairs if r.get("area") is not None]
    cuts = area_bands(areas) if len(areas) >= 3 else None
    by_band: dict[str, dict] = {}
    if cuts:
        for band in ("small", "medium", "large"):
            sel = [r for r in pairs if r.get("area") is not None and band_for(r["area"], cuts) == band]
            k = sum(1 for r in sel if r["arms"]["a"]["top1"] == r["arms"]["b"]["top1"])
            by_band[band] = {"pairs": len(sel), "agree": k, "disagree": len(sel) - k}
    deltas = [r["arms"]["b"]["conf"] - r["arms"]["a"]["conf"] for r in pairs]
    min_conf = next((r["min_confidence"] for r in rows if r.get("min_confidence") is not None), None)
    stored = None
    if min_conf is not None:
        k = sum(1 for r in pairs if stored_outcome(r["arms"]["a"], min_conf) == stored_outcome(r["arms"]["b"], min_conf))
        stored = {"min_confidence": min_conf, "n": k, "of": len(pairs),
                  "rate": k / len(pairs) if pairs else None, "wilson95": wilson(k, len(pairs))}
    out = {
        "frames": len(rows),
        "failed": {"a": sum(1 for r in rows if not _ok(r["arms"]["a"])),
                   "b": sum(1 for r in rows if not _ok(r["arms"]["b"]))},
        "pairs": len(pairs),
        "top1_agree": {"n": len(agree), "of": len(pairs),
                       "rate": len(agree) / len(pairs) if pairs else None,
                       "wilson95": wilson(len(agree), len(pairs))},
        "top1_conf_delta_b_minus_a": {"mean": sum(deltas) / len(deltas) if deltas else None},
        "box_iou": {"pairs_with_both_boxes": len(with_both_boxes),
                    "median": sorted(with_both_boxes)[len(with_both_boxes) // 2] if with_both_boxes else None,
                    "different_box": sum(1 for v in with_both_boxes if v < DIFFERENT_BOX_IOU),
                    "different_box_iou_lt": DIFFERENT_BOX_IOU,
                    "b_without_box": sum(1 for r in pairs if r["arms"]["b"].get("box") is None),
                    "a_without_box": sum(1 for r in pairs if r["arms"]["a"].get("box") is None)},
        "area_band_cuts": list(cuts) if cuts else None,
        "by_area_band": by_band,
        "aspect_mismatch": sum(1 for r in rows if r.get("aspect_mismatch")),
        "aspect_unknown": sum(1 for r in rows if r.get("aspect_mismatch") is None),
        "stored_output_agree": stored,
        "disagreements": [{"image_id": r["image_id"], "a": r["arms"]["a"]["top1"], "b": r["arms"]["b"]["top1"],
                           "iou": box_iou(r["arms"]["a"].get("box"), r["arms"]["b"].get("box"))}
                          for r in pairs if r["arms"]["a"]["top1"] != r["arms"]["b"]["top1"]],
    }
    if by_version:
        versions = sorted({r.get("detector_version") or "unknown" for r in rows})
        out["by_detector_version"] = {
            v: compare([r for r in rows if (r.get("detector_version") or "unknown") == v], by_version=False)
            for v in versions} if len(versions) > 1 else {}
    return out


def parse_arm(spec: str) -> tuple[str, str | None]:
    """``embedded`` or ``region:<field>``."""
    if spec == "embedded":
        return "embedded", None
    kind, _, field = spec.partition(":")
    if kind != "region" or not field:
        raise ValueError(f"arm must be 'embedded' or 'region:<field>', got {spec!r}")
    return "region", field


def draw(pool: list[dict], *, seed: int, size: int) -> list[dict]:
    """Seeded simple random draw, sorted by image_id."""
    if len(pool) < size:
        raise ValueError(f"pool has {len(pool)} frames, needs {size}")
    ordered = sorted(pool, key=lambda f: f["image_id"])
    return sorted(random.Random(seed).sample(ordered, size), key=lambda f: f["image_id"])


# --------------------------------------------------------------------------- DB / GPU modes

def sample(out: Path, *, seed: int, size: int, exclude_manifest: Path | None) -> dict:
    from modules import db

    if out.exists():
        raise FileExistsError(out)
    excluded = set()
    if exclude_manifest:
        excluded = {int(i["image_id"]) for i in json.loads(exclude_manifest.read_text(encoding="utf-8"))["items"]}
    rows = db.get_connector().query(_COHORT_SQL)
    pool = []
    for r in rows:
        if int(r["image_id"]) in excluded:
            continue
        box = [r["x1"], r["y1"], r["x2"], r["y2"]]
        pool.append({"image_id": int(r["image_id"]), "file_path": r["file_path"], "run_id": int(r["run_id"]),
                     "region_id": int(r["region_id"]), "detector_version": r["detector_version"],
                     "display": [r["display_width"], r["display_height"]],
                     "confidence": r["confidence"], "box": box, "area": box_area(box)})
    frames = draw(pool, seed=seed, size=size)
    with out.open("x", encoding="utf-8") as fh:
        for f in frames:
            fh.write(json.dumps(f) + "\n")
    meta = {"schema": SCHEMA, "seed": seed, "size": size, "cohort": len(rows), "excluded": len(excluded),
            "pool": len(pool), "versions": dict(Counter(f["detector_version"] for f in frames)),
            "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}
    print(json.dumps(meta))
    return meta


def _classify(clf, species, path, kind, frame, field) -> dict:
    if kind == "embedded":
        res = clf.classify(path, species, threshold=0.0, top_k=1, use_detector=True)
        box = normalized_pixel_box(clf.last_bbox)
    else:
        box = frame.get(field)
        if box is None:
            return {"error": f"no {field}"}
        res = clf.classify(path, species, threshold=0.0, top_k=1, region=tuple(box), use_detector=False)
    if not res:
        return {"error": clf.last_error or "no result", "box": box}
    return {"top1": res[0][0], "conf": res[0][1], "box": box, "input_mode": clf.last_input_mode}


def run(sample_path: Path, out: Path, arm_a: str, arm_b: str) -> Counter:
    from modules.bird_species import (
        _load_default_species,
        _resolve_inference_path,
        min_confidence,
        new_bioclip_classifier,
    )
    from modules.thumbnails import open_oriented_for_ml

    arms = {"a": parse_arm(arm_a), "b": parse_arm(arm_b)}
    species = _load_default_species()
    if not species:
        raise RuntimeError("species list is empty")
    clf = new_bioclip_classifier()
    min_conf = min_confidence()
    frames = [json.loads(line) for line in sample_path.read_text(encoding="utf-8").splitlines() if line]
    done = set()
    if out.exists():
        done = {json.loads(line)["image_id"] for line in out.read_text(encoding="utf-8").splitlines() if line}
    counts: Counter = Counter()
    with out.open("a", encoding="utf-8") as fh:
        for n, frame in enumerate(frames, 1):
            if frame["image_id"] in done:
                continue
            path = _resolve_inference_path(frame, frame["file_path"])
            rec = {"schema": SCHEMA, "image_id": frame["image_id"], "area": frame.get("area"),
                   "detector_version": frame.get("detector_version"), "min_confidence": min_conf,
                   "arm_specs": {"a": arm_a, "b": arm_b}, "inference_path": path, "arms": {}}
            try:
                size = list(open_oriented_for_ml(path).size)
            except Exception as exc:  # noqa: BLE001 — recorded per frame
                size = None
                rec["decode_error"] = f"{type(exc).__name__}: {exc}"[:200]
            rec["size"] = size
            rec["aspect_mismatch"] = aspect_mismatch(size, frame.get("display"))
            for key, (kind, field) in arms.items():
                rec["arms"][key] = _classify(clf, species, path, kind, frame, field)
            counts["ok" if all(_ok(a) for a in rec["arms"].values()) else "failed"] += 1
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if n % 25 == 0:
                print(f"species-parity {n}/{len(frames)} {dict(counts)}", flush=True)
    return counts


def report(results: Path, out: Path) -> dict:
    rows = [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines() if line]
    rep = {"schema": SCHEMA, "results": str(results),
           "results_sha256": hashlib.sha256(results.read_bytes()).hexdigest(),
           "arm_specs": rows[0]["arm_specs"] if rows else None, **compare(rows)}
    out.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("pairs", "top1_agree", "stored_output_agree", "box_iou", "aspect_mismatch")},
                     indent=1))
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--size", type=int, default=200)
    s.add_argument("--exclude-manifest", type=Path)
    r = sub.add_parser("run")
    r.add_argument("--sample", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--arm-a", default="region:box")
    r.add_argument("--arm-b", default="embedded")
    p = sub.add_parser("report")
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.mode == "sample":
        sample(a.out, seed=a.seed, size=a.size, exclude_manifest=a.exclude_manifest)
    elif a.mode == "run":
        print(dict(run(a.sample, a.out, a.arm_a, a.arm_b)))
    else:
        report(a.results, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
