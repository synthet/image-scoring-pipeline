"""Run the detector benchmark arms over a pinned cohort (#377). GPU, gpu-shell only.

    python scripts/research/detector_benchmark/run_benchmark.py \
        --cohort <dir>/cohort.csv --out <dir> [--limit 5]

Each frame is decoded **once**, exactly as production decodes it
(``modules/bird_species.py`` scan path): ``open_rendition_for_ml`` -> ``.convert("RGB")``
-> ``bake_orientation``. Every arm then runs on those same pixels, so a difference between
arms is the detector's, never the decoder's. The same decode also writes the upright
labelling thumbnail, which is why labelling can happen after this run: the arms don't
need labels, only the scoring step does.

Arms
----
``a640``    ``imgsz=640``, ``conf=0.25`` -- production.
``a1280``   ``imgsz=1280``, ``conf=0.25``.
``tile``    ``a640``, then *only on a miss* a 2x2 tiling with 20% overlap, each tile at
            ``imgsz=640``; tile boxes are mapped back to full-frame coordinates and merged
            with NMS (IoU 0.5). A hit keeps its ``a640`` result.

Plus a diagnostic, not an arm: the best confidence YOLO produces at ``conf=0.05``,
``imgsz=640``. It answers "would lowering ``conf`` alone recover the misses?".

All arms share one loaded model; only ``imgsz`` / ``confidence`` change between calls.
Production defaults in ``config.json`` are never read or changed -- values are explicit.

Resumable: frames already present in ``results.csv`` are skipped.
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger("run_benchmark")

PROD_CONF = 0.25
DIAG_CONF = 0.05
MAX_DET = 10
TILE_GRID = 2
TILE_OVERLAP = 0.20
NMS_IOU = 0.5
LABEL_EDGE = 384

ARMS = ("a640", "a1280", "tile")

FIELDS = (
    ["image_id", "stratum", "decode_route", "img_w", "img_h", "decode_ms"]
    + [f"{a}_{k}" for a in ARMS for k in ("n", "top_conf", "top_area_frac", "suspicious", "ms")]
    + ["tile_ran", "diag_max_conf"]
)


def _sync():
    import torch

    if torch.cuda.is_available():
        torch.cuda.synchronize()


def _timed(fn):
    _sync()
    t0 = time.perf_counter()
    out = fn()
    _sync()
    return out, (time.perf_counter() - t0) * 1000.0


def _raw(det, image, imgsz, conf):
    det.imgsz, det.confidence = imgsz, conf
    return det._predict_raw_boxes(image)


def _tiles(w, h):
    """2x2 tiles covering the frame, each overlapping its neighbour by TILE_OVERLAP."""
    tw = math.ceil(w * (1 + TILE_OVERLAP) / TILE_GRID)
    th = math.ceil(h * (1 + TILE_OVERLAP) / TILE_GRID)
    xs = [0, max(0, w - tw)]
    ys = [0, max(0, h - th)]
    return [(x, y, min(w, x + tw), min(h, y + th)) for y in ys for x in xs]


def _tile_pass(det, image):
    import torch
    from torchvision.ops import nms

    w, h = image.size
    boxes = []
    for x0, y0, x1, y1 in _tiles(w, h):
        for b in _raw(det, image.crop((x0, y0, x1, y1)), 640, PROD_CONF):
            bx1, by1, bx2, by2 = b["xyxy"]
            boxes.append({"xyxy": (bx1 + x0, by1 + y0, bx2 + x0, by2 + y0), "conf": b["conf"]})
    if len(boxes) < 2:
        return boxes
    t = torch.tensor([b["xyxy"] for b in boxes], dtype=torch.float32)
    s = torch.tensor([b["conf"] for b in boxes], dtype=torch.float32)
    keep = nms(t, s, NMS_IOU).tolist()
    return [boxes[i] for i in keep]


def _summ(ranked):
    if not ranked:
        return {"n": 0, "top_conf": "", "top_area_frac": "", "suspicious": 0}
    top = ranked[0]
    return {"n": len(ranked), "top_conf": top["conf"], "top_area_frac": top["area_frac"],
            "suspicious": int(any(b["suspicious"] for b in ranked))}


def _decode(path):
    from modules.thumbnails import bake_orientation, open_rendition_for_ml

    img, route = open_rendition_for_ml(path)
    img = img.convert("RGB")
    try:
        img = bake_orientation(img, path)
    except Exception as exc:  # noqa: BLE001 -- mirror production: orientation is best-effort
        logger.debug("bake_orientation failed for %s: %s", path, exc)
    return img, route


def _done_ids(results_csv):
    if not results_csv.exists():
        return set()
    with open(results_csv, newline="", encoding="utf-8") as fh:
        return {int(r["image_id"]) for r in csv.DictReader(fh)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=None, help="Stop after N new frames")
    ap.add_argument("--no-thumbs", action="store_true", help="Skip labelling thumbnails")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import torch

    from modules.bird_detection import BirdDetector, rank_boxes

    out = Path(args.out)
    thumbs = out / "label_thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    results_csv = out / "results.csv"
    done = _done_ids(results_csv)

    with open(args.cohort, newline="", encoding="utf-8") as fh:
        cohort = [r for r in csv.DictReader(fh) if int(r["image_id"]) not in done]
    if args.limit:
        cohort = cohort[: args.limit]
    logger.info("%d frames to run (%d already done)", len(cohort), len(done))

    det = BirdDetector(config={"max_det": MAX_DET, "confidence": PROD_CONF, "imgsz": 640})
    det.load_model()

    # Warm up both input sizes so the first timed frame doesn't pay for CUDA init.
    from PIL import Image
    warm = Image.new("RGB", (1024, 768))
    for sz in (640, 1280):
        _raw(det, warm, sz, PROD_CONF)

    peak = {a: 0 for a in ARMS}
    new_file = not results_csv.exists()
    with open(results_csv, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for i, row in enumerate(cohort, 1):
            path = row["file_path"]
            try:
                (img, route), dec_ms = _timed(lambda: _decode(path))
            except Exception as exc:  # noqa: BLE001 -- record and continue
                logger.warning("decode failed for %s: %s", path, exc)
                continue
            iw, ih = img.size
            rec = {"image_id": row["image_id"], "stratum": row["stratum"],
                   "decode_route": route.value, "img_w": iw, "img_h": ih,
                   "decode_ms": round(dec_ms, 1)}

            results = {}
            for arm, sz in (("a640", 640), ("a1280", 1280)):
                if torch.cuda.is_available():
                    torch.cuda.reset_peak_memory_stats()
                raw, ms = _timed(lambda: _raw(det, img, sz, PROD_CONF))
                if torch.cuda.is_available():
                    peak[arm] = max(peak[arm], torch.cuda.max_memory_allocated())
                results[arm] = (rank_boxes(raw, iw, ih, MAX_DET), ms)

            a640_ranked, a640_ms = results["a640"]
            tile_ran = not a640_ranked
            if tile_ran:
                if torch.cuda.is_available():
                    torch.cuda.reset_peak_memory_stats()
                raw, ms = _timed(lambda: _tile_pass(det, img))
                if torch.cuda.is_available():
                    peak["tile"] = max(peak["tile"], torch.cuda.max_memory_allocated())
                results["tile"] = (rank_boxes(raw, iw, ih, MAX_DET), a640_ms + ms)
            else:
                results["tile"] = (a640_ranked, a640_ms)

            for arm in ARMS:
                ranked, ms = results[arm]
                for k, v in _summ(ranked).items():
                    rec[f"{arm}_{k}"] = v
                rec[f"{arm}_ms"] = round(ms, 1)
            rec["tile_ran"] = int(tile_ran)

            diag = _raw(det, img, 640, DIAG_CONF)
            rec["diag_max_conf"] = round(max((b["conf"] for b in diag), default=0.0), 4)

            if not args.no_thumbs:
                t = img.copy()
                t.thumbnail((LABEL_EDGE, LABEL_EDGE))
                t.save(thumbs / f"{row['image_id']}.jpg", "JPEG", quality=85)

            w.writerow(rec)
            fh.flush()
            if i % 10 == 0 or i == len(cohort):
                logger.info("%d/%d  last: %s a640=%s a1280=%s tile=%s",
                            i, len(cohort), row["stratum"], rec["a640_n"], rec["a1280_n"], rec["tile_n"])

    with open(out / "gpu_peak_bytes.csv", "w", newline="", encoding="utf-8") as fh:
        pw = csv.writer(fh)
        pw.writerow(["arm", "peak_bytes"])
        for arm in ARMS:
            pw.writerow([arm, peak[arm]])
    logger.info("peak GPU memory (MiB): %s", {a: round(v / 2**20) for a, v in peak.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
