#!/usr/bin/env python3
"""Spec 08 AC-9: does the pipeline's RTMDet agree with the benchmark's at the agreement limit?

Reads the model repository's benchmark predictions (per-box ``agree`` scores) and re-scores each
box with the pipeline's ONNX provider on the same rendition. Read-only; writes one JSON receipt.

Usage:
  python scripts/research/detector_benchmark/agreement_parity.py --model-repo ../image-scoring-model \
      --sample data/field_eye_calib_v1 --predictions data/eye_benchmark/calib_v1_crop/B_tdc.predictions.jsonl \
      --out parity.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from modules.detectors.rtmdet import load_rtmdet  # noqa: E402
from modules.localization_agreement import AGREEMENT_LIMIT, SCORE_FLOOR, agreement_score, padded_crop  # noqa: E402

PASS_RATE = 0.95


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="Spec 08 AC-9 RTMDet parity check")
    ap.add_argument("--model-repo", type=Path, required=True)
    ap.add_argument("--sample", required=True, help="Labelled sample folder, relative to the model repository")
    ap.add_argument("--predictions", required=True, help="Benchmark predictions with `agree`, relative to the model repository")
    ap.add_argument("--weights", default=str(REPO_ROOT / "models" / "rtmdet_tiny_coco.onnx"))
    ap.add_argument("--bird-conf", type=float, default=0.25, help="Only compare boxes at or above this detector score")
    ap.add_argument("--limit", type=float, default=AGREEMENT_LIMIT)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    from PIL import Image

    provider = load_rtmdet(args.weights, threshold=SCORE_FLOOR, retry_threshold=None)
    if not provider.enabled:
        print(f"RTMDet unavailable: {provider.error_code}: {provider.error_detail}")
        return 2

    manifest = {r["image_id"]: r for r in jsonl(args.model_repo / args.sample / "manifest.jsonl")}
    rows = []
    for frame in jsonl(args.model_repo / args.predictions):
        dets = [d for d in frame.get("detections", []) if d["confidence"] >= args.bird_conf and "agree" in d]
        if not dets:
            continue
        with Image.open(args.model_repo / manifest[frame["image_id"]]["image_path"]) as src:
            image = src.convert("RGB")
        width, height = image.size
        for det in dets:
            x1, y1, x2, y2 = det["bbox"]
            region = (x1 / width, y1 / height, x2 / width, y2 / height)
            crop = padded_crop(region, width, height)
            if crop is None:
                continue
            score = agreement_score(region, crop, provider.detect(image.crop(crop)), width, height)
            rows.append({"image_id": frame["image_id"], "benchmark": det["agree"], "pipeline": round(score, 4)})

    same = sum((r["benchmark"] >= args.limit) == (r["pipeline"] >= args.limit) for r in rows)
    rate = same / len(rows) if rows else 0.0
    passed = bool(rows) and rate >= PASS_RATE
    receipt = {
        "predictions": args.predictions, "bird_conf": args.bird_conf, "limit": args.limit, "regions": len(rows),
        "same_decision": same, "rate": round(rate, 4), "required": PASS_RATE, "passed": passed,
        "benchmark_pass": sum(r["benchmark"] >= args.limit for r in rows),
        "pipeline_pass": sum(r["pipeline"] >= args.limit for r in rows),
        "largest_score_gaps": sorted(rows, key=lambda r: -abs(r["benchmark"] - r["pipeline"]))[:10],
    }
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k != "largest_score_gaps"}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
