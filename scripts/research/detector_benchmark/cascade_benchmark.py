#!/usr/bin/env python3
"""Cascade benchmark on the #377 cohort (spec 03 AC-16, open question 4). Read-only for the DB.

    python scripts/research/detector_benchmark/cascade_benchmark.py \
        --dir docs/reports/detector-benchmark-2026-09 --out <scratch dir>

Per frame, one decode (the localization decoder), then:
  * ``yolo``: the production bird detector (``BirdDetector.detect_boxes``);
  * ``coco``: RTMDet-tiny through onnxruntime on the upstream export (weights hash verified), all
    animal boxes >= 0.05 kept raw so every threshold policy is applied offline;
  * refine: for small COCO boxes, YOLO on the padded crop (policy ``refine_v1``).
Raw per-frame results go to ``<out>/raw.jsonl`` (resumable); ``<out>/cascade_metrics.md`` reports
recall on ``bird`` frames and false-positive rate on ``no_bird`` frames with Wilson 95% intervals,
per stratum group, for YOLO, COCO and cascade arms at several COCO operating points, plus the
agreement arm (YOLO boxes kept only when COCO also sees an animal).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

GROUPS = {"independent": ("miss_birdkw", "miss_nokw"), "det_*": ("det_small", "det_medium", "det_large"),
          "eagle": ("eagle",)}
POLICIES = [(0.40, 0.25), (0.40, None), (0.50, None), (0.60, None), (0.70, None)]


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, max(0.0, c - h), min(1.0, c + h)


def fmt(k, n):
    p, lo, hi = wilson(k, n)
    return f"{k}/{n} ({p:.0%}, {lo:.0%}-{hi:.0%})" if n else "-"


def coco_hit(boxes, thr, retry):
    if any(b["conf"] >= thr for b in boxes):
        return True
    return retry is not None and any(b["conf"] >= retry for b in boxes)


def collect(a) -> None:
    from modules import db
    from modules.bird_detection import BirdDetector
    from modules.detectors.rtmdet import load_rtmdet, select_animal_boxes, letterbox
    from modules.localization import decode_for_localization
    from modules.localization_cascade import REFINE_PAD_FRAC, refine_crop
    import numpy as np

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    raw_path = out / "raw.jsonl"
    done = {json.loads(line)["image_id"] for line in raw_path.open()} if raw_path.exists() else set()
    cohort = list(csv.DictReader(open(Path(a.dir) / "cohort.csv")))
    rt = load_rtmdet(a.weights)
    if not rt.enabled:
        raise SystemExit(f"rtmdet disabled: {rt.error_code} {rt.error_detail}")
    yolo = BirdDetector()
    yolo.load_model()
    conn = db.get_connector()
    with raw_path.open("a") as fh:
        for n, row in enumerate(cohort, 1):
            iid = int(row["image_id"])
            if iid in done:
                continue
            rec = {"image_id": iid, "stratum": row["stratum"]}
            path = (conn.query_one("SELECT file_path FROM images WHERE id = ?", (iid,)) or {}).get("file_path")
            try:
                img = decode_for_localization(path).image
                w, h = img.size
                rec["yolo"] = [{"region": b["region"], "conf": b["conf"]} for b in yolo.detect_boxes(img)]
                x, scale, px, py = letterbox(img, rt.mean, rt.std)
                outs = rt.session.run(None, {rt.session.get_inputs()[0].name: x})
                boxes = (np.asarray(outs[0])[0].astype(np.float64) - [px, py, px, py]) / scale
                boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w)
                boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h)
                coco = select_animal_boxes(boxes, np.asarray(outs[1])[0], w, h, threshold=0.05, retry_threshold=0.05)
                rec["coco"] = [{"region": b["region"], "conf": b["conf"], "cls": b["cls"]} for b in coco]
                refined = []
                for b in coco:
                    reg = b["region"]
                    if b["conf"] < 0.25 or (reg[2] - reg[0]) * (reg[3] - reg[1]) >= a.refine_area_frac:
                        continue
                    c = refine_crop(reg, REFINE_PAD_FRAC)
                    crop = img.crop((int(c[0] * w), int(c[1] * h), int(c[2] * w), int(c[3] * h)))
                    cw, ch = crop.size
                    got = [{"region": (c[0] + r["region"][0] * cw / w, c[1] + r["region"][1] * ch / h,
                                       c[0] + r["region"][2] * cw / w, c[1] + r["region"][3] * ch / h),
                            "conf": r["conf"]} for r in yolo.detect_boxes(crop)]
                    refined.append({"coco_region": reg, "yolo": got})
                rec["refine"] = refined
            except Exception as exc:  # noqa: BLE001
                rec["error"] = str(exc)[:200]
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if n % 25 == 0:
                print(f"{n}/{len(cohort)}", file=sys.stderr, flush=True)


def report(a) -> None:
    from modules.localization_cascade import REFINE_MIN_IOU, iou

    out = Path(a.out)
    recs = [json.loads(line) for line in (out / "raw.jsonl").open()]
    labels = {int(r["image_id"]): r["label"] for r in csv.DictReader(open(Path(a.dir) / "labels.csv"))}
    recs = [r for r in recs if "error" not in r]

    arms = {"yolo": lambda r: bool(r["yolo"])}
    for thr, retry in POLICIES:
        tag = f"{thr:.2f}" + (f"/{retry:.2f}" if retry else "")
        arms[f"coco@{tag}"] = (lambda r, t=thr, rr=retry: coco_hit(r["coco"], t, rr))
        arms[f"cascade@{tag}"] = (lambda r, t=thr, rr=retry: bool(r["yolo"]) or coco_hit(r["coco"], t, rr))
        arms[f"agree@{tag}"] = (lambda r, t=thr, rr=retry: coco_hit(r["coco"], t, rr))  # yolo kept only if coco sees
    lines = ["# Cascade benchmark (#408, spec 03 AC-16)", "",
             f"Frames: {len(recs)} of the #377 cohort; labels from `labels.csv` (owner). Presence only: a frame "
             "counts as detected when the arm returns at least one box. Wilson 95% intervals. `agree@t` keeps a "
             "YOLO box only when COCO also sees an animal at t, and otherwise falls back to COCO at t, so its "
             "presence equals `coco@t`.", ""]
    for gname, strata in GROUPS.items():
        g = [r for r in recs if r["stratum"] in strata]
        birds = [r for r in g if labels.get(r["image_id"]) == "bird"]
        nob = [r for r in g if labels.get(r["image_id"]) == "no_bird"]
        lines += [f"## {gname} ({len(birds)} bird, {len(nob)} no_bird)", "",
                  "| arm | recall (bird) | false positives (no_bird) |", "|---|---|---|"]
        for name, fn in arms.items():
            if name.startswith("agree"):
                continue
            lines.append(f"| {name} | {fmt(sum(fn(r) for r in birds), len(birds))} | "
                         f"{fmt(sum(fn(r) for r in nob), len(nob))} |")
        lines.append("")
    # refine pass
    tried = ok = 0
    for r in recs:
        for f in r.get("refine", []):
            tried += 1
            if any(iou(tuple(y["region"]), tuple(f["coco_region"])) >= REFINE_MIN_IOU for y in f["yolo"]):
                ok += 1
    lines += ["## Refine pass", "", f"Small COCO boxes (< {a.refine_area_frac:.0%} of frame, conf >= 0.25) "
              f"re-run through YOLO on a crop: {tried}; refined (IoU >= {REFINE_MIN_IOU}): {ok}.", ""]
    (out / "cascade_metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, help="benchmark dir with cohort.csv and labels.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--weights", default=os.path.join(_ROOT, "models", "rtmdet_tiny_coco.onnx"))
    ap.add_argument("--refine-area-frac", type=float, default=0.02)
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    if not a.report_only:
        collect(a)
    report(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
