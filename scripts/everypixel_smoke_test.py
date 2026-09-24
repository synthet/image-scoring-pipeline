#!/usr/bin/env python3
"""Smoke-test Everypixel sync APIs on a few local images (network + credentials required).

RAW/NEF paths are converted to JPEG before upload via ``prepare_jpeg_for_api``.
Loads ``EVERYPIXEL_*`` from repo ``.env`` when present (does not print secrets).

Example (gpu-shell):

    scripts/batch/docker_gpu_run.bat scripts/everypixel_smoke_test.py --limit 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _default_image_paths(limit: int) -> list[Path]:
    from tests.support.testing_samples import list_sample_image_files

    samples = [Path(p) for p in list_sample_image_files()]
    nefs = [p for p in samples if p.suffix.lower() == ".nef"]
    chosen: list[Path] = []
    favicon = REPO_ROOT / "static" / "favicon.png"
    jpegs = [p for p in samples if p.suffix.lower() in {".jpg", ".jpeg"}]
    chosen.extend(nefs[:limit])
    if len(chosen) < limit and jpegs:
        chosen.append(jpegs[0])
    if len(chosen) < limit and favicon.is_file():
        chosen.append(favicon)
    while len(chosen) < limit and len(samples) > len(chosen):
        for p in samples:
            if p not in chosen:
                chosen.append(p)
                break
        else:
            break
    return chosen[:limit]


def _summarize_result(block: dict) -> dict:
    endpoints = block.get("endpoints") or {}
    summary: dict = {
        "source_path": block.get("source_path"),
        "quality_stock": None,
        "quality_ugc": None,
        "ugc_class": None,
        "caption": None,
        "keyword_count": 0,
        "top_keywords": [],
        "face_count": 0,
        "errors": block.get("errors") or {},
    }
    stock = endpoints.get("stock") or {}
    ugc = endpoints.get("ugc") or {}
    if isinstance(stock.get("quality"), dict):
        summary["quality_stock"] = stock["quality"].get("score")
    if isinstance(ugc.get("quality"), dict):
        summary["quality_ugc"] = ugc["quality"].get("score")
        summary["ugc_class"] = ugc["quality"].get("class")
    cap = endpoints.get("captioning") or {}
    if isinstance(cap.get("result"), dict):
        summary["caption"] = cap["result"].get("caption")
    kw = endpoints.get("keywords") or {}
    keywords = kw.get("keywords") or []
    if isinstance(keywords, list):
        summary["keyword_count"] = len(keywords)
        summary["top_keywords"] = [
            k.get("keyword") for k in keywords[:5] if isinstance(k, dict)
        ]
    faces = endpoints.get("faces") or {}
    face_list = faces.get("faces") or []
    if isinstance(face_list, list):
        summary["face_count"] = len(face_list)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Everypixel API smoke test")
    parser.add_argument(
        "images",
        nargs="*",
        help="Image paths (RAW ok). Default: testing_samples NEFs + favicon.png",
    )
    parser.add_argument("--limit", type=int, default=3, help="Default path count when no args")
    parser.add_argument(
        "--usage-state",
        default="",
        help="Optional JSON path for persistent usage counters",
    )
    args = parser.parse_args()

    _load_dotenv(REPO_ROOT / ".env")
    if args.usage_state:
        os.environ["EVERYPIXEL_USAGE_STATE_PATH"] = args.usage_state

    paths = [Path(p) for p in args.images] if args.images else _default_image_paths(args.limit)
    paths = [p for p in paths if p.is_file()]
    if not paths:
        print("No image files found.", file=sys.stderr)
        return 2

    from modules.everypixel import EverypixelClient

    client = EverypixelClient()
    report: dict = {"images": [], "summaries": [], "usage": None}

    for path in paths:
        print(f"Analyzing {path} ...", flush=True)
        block = client.analyze_sync(path)
        report["images"].append(block)
        report["summaries"].append(_summarize_result(block))

    report["usage"] = client.usage_summary()
    print(json.dumps(report, indent=2, default=str))
    if any(block.get("errors") for block in report["images"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
