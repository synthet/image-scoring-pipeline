#!/usr/bin/env python3
"""Measure the decode-once rendition against the full-size localization decode (#406).

Read-only for the database. Writes renditions to a scratch cache dir (default: a temp dir), never
to the shared cache.

For each sampled RAW image of a folder:
  * decode time: full-size localization decode, rendition miss, rendition hit (AC-13 evidence);
  * bird detector on full size vs the 2048 px rendition: rank-0 box IoU (normalized coordinates);
  * optional (when ``modules.keypoints`` is importable): eye keypoints on the full-size region vs
    the 2048 px region, distance between the eyes found >= 0.8 in both, as a fraction of the
    region diagonal.

    python scripts/research/rendition/measure_rendition.py --folder /mnt/d/Photos/... --limit 60
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u > 0 else 0.0


def _pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True, help="exact folders.path")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--cache-dir", default="")
    ap.add_argument("--birds-only", action="store_true", help="only images whose legacy box found a bird")
    a = ap.parse_args()

    from modules import db
    from modules.bird_detection import BirdDetector
    from modules.localization import decode_for_localization
    from modules.rendition_cache import get_inference_rendition

    try:
        from modules.keypoints import infer_region_keypoints, load_keypoint_context

        kctx = load_keypoint_context({"keypoints": {"bird_head": {"enabled": True}}})
        kctx = None if kctx.load_error else kctx
    except ImportError:
        kctx = None

    cache_dir = a.cache_dir or tempfile.mkdtemp(prefix="rendition-measure-")
    rows = db.get_connector().query(
        "SELECT i.id, i.file_path FROM images i JOIN folders f ON f.id = i.folder_id "
        "WHERE f.path = ? AND lower(i.file_path) LIKE '%.nef'"
        + (" AND (i.bird_bbox ->> 'img_w') IS NOT NULL" if a.birds_only else "")
        + " ORDER BY i.id",
        (a.folder,))[: a.limit]
    det = BirdDetector()
    det.load_model()

    t_full, t_miss, t_hit, ious, eye_d, box_counts = [], [], [], [], [], {"both": 0, "full_only": 0, "rend_only": 0,
                                                                          "neither": 0}
    for r in rows:
        path = r["file_path"]
        if not os.path.exists(path):
            continue
        t0 = time.perf_counter()
        full = decode_for_localization(path)
        t_full.append(time.perf_counter() - t0)
        rimg, _, info = get_inference_rendition(path, cache_dir=cache_dir)
        t_miss.append(info["seconds"])
        rimg, _, info = get_inference_rendition(path, cache_dir=cache_dir)
        t_hit.append(info["seconds"])

        bf = det.detect_boxes(full.image)
        br = det.detect_boxes(rimg)
        key = ("both" if bf and br else "full_only" if bf else "rend_only" if br else "neither")
        box_counts[key] += 1
        if not (bf and br):
            continue
        ious.append(_iou(bf[0]["region"], br[0]["region"]))
        if kctx is not None:
            reg = tuple(bf[0]["region"])
            kf = infer_region_keypoints(kctx, full.image, reg)["keypoints"]
            kr = infer_region_keypoints(kctx, rimg, reg)["keypoints"]
            diag = ((reg[2] - reg[0]) ** 2 + (reg[3] - reg[1]) ** 2) ** 0.5
            for pf, pr in zip(kf, kr):
                if pf["name"].endswith("_eye") and pf["confidence"] >= 0.8 and pr["confidence"] >= 0.8:
                    eye_d.append(((pf["x"] - pr["x"]) ** 2 + (pf["y"] - pr["y"]) ** 2) ** 0.5 / diag)

    out = {
        "images": len(t_full),
        "decode_s": {name: {"p50": round(_pct(v, 0.5), 3), "p95": round(_pct(v, 0.95), 3)}
                     for name, v in (("full", t_full), ("rendition_miss", t_miss), ("rendition_hit", t_hit))},
        "detector": {**box_counts, "rank0_iou_median": round(statistics.median(ious), 4) if ious else None,
                     "rank0_iou_p10": round(_pct(ious, 0.1), 4) if ious else None,
                     "iou_below_0.9": sum(1 for v in ious if v < 0.9)},
        "eyes": ({"pairs": len(eye_d), "median_frac_of_diag": round(statistics.median(eye_d), 4),
                  "p90_frac_of_diag": round(_pct(eye_d, 0.9), 4)} if eye_d else None),
        "cache_dir": cache_dir,
    }
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
