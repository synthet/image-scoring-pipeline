#!/usr/bin/env python3
"""Fetch Everypixel UGC quality for manifest images → JSONL (network + credentials).

Uses ``EverypixelClient.score(..., model=\"ugc\")`` only. RAW paths are converted to
JPEG before upload. Respects ``EVERYPIXEL_SPEND_LIMIT_USD`` and usage state file.

Run in gpu-shell::

    scripts/batch/docker_gpu_run.bat scripts/research/everypixel_correlation/fetch_ugc.py \\
        --manifest reports/everypixel-correlation/manifest.json --limit 5
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.research.everypixel_correlation.common import DEFAULT_MANIFEST, DEFAULT_UGC_JSONL

logger = logging.getLogger(__name__)


def _load_dotenv(repo_root: Path) -> None:
    env_path = repo_root / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _read_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_existing_jsonl(path: Path) -> dict[int, dict[str, Any]]:
    if not path.is_file():
        return {}
    done: dict[int, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("status") == "ok" and row.get("image_id") is not None:
            done[int(row["image_id"])] = row
    return done


def fetch_ugc(
    *,
    manifest_path: Path,
    out_path: Path,
    limit: int | None,
    sleep_sec: float,
    skip_existing: bool,
) -> Path:
    from modules.everypixel import EverypixelClient, EverypixelBudgetExceeded, EverypixelError

    repo_root = Path(__file__).resolve().parents[3]
    _load_dotenv(repo_root)

    manifest = _read_manifest(manifest_path)
    images = manifest.get("images") or []
    if limit is not None:
        images = images[: int(limit)]

    existing = _load_existing_jsonl(out_path) if skip_existing else {}
    client = EverypixelClient()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if out_path.is_file() and skip_existing else "w"
    n_ok = 0
    n_err = 0

    with out_path.open(mode, encoding="utf-8") as out_f:
        for row in images:
            image_id = int(row["image_id"])
            file_path = str(row["file_path"])
            if skip_existing and image_id in existing:
                logger.info("skip image_id=%s (already ok in jsonl)", image_id)
                continue

            record: dict[str, Any] = {
                "image_id": image_id,
                "file_path": file_path,
                "general_quintile": row.get("general_quintile"),
                "score_general": row.get("score_general"),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "status": "error",
                "ugc_score": None,
                "ugc_class": None,
                "error": None,
            }
            path = Path(file_path)
            if not path.is_file():
                record["error"] = "file_not_found"
                n_err += 1
                out_f.write(json.dumps(record) + "\n")
                continue

            try:
                payload = client.score(path, model="ugc")
                quality = payload.get("quality") or {}
                record["status"] = "ok"
                record["ugc_score"] = float(quality.get("score"))
                cls = quality.get("class")
                record["ugc_class"] = int(cls) if cls is not None else None
                n_ok += 1
            except EverypixelBudgetExceeded as exc:
                record["error"] = str(exc)
                out_f.write(json.dumps(record) + "\n")
                logger.error("budget exceeded after %d ok, %d err", n_ok, n_err)
                break
            except (EverypixelError, OSError, ValueError) as exc:
                record["error"] = str(exc)
                n_err += 1

            out_f.write(json.dumps(record) + "\n")
            out_f.flush()
            if sleep_sec > 0:
                time.sleep(sleep_sec)

    summary = client.usage_summary()
    logger.info(
        "fetch complete: ok=%d err=%d usage=%s",
        n_ok,
        n_err,
        json.dumps(summary, sort_keys=True),
    )
    return out_path


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Fetch Everypixel UGC scores for cohort")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_UGC_JSONL)
    parser.add_argument("--limit", type=int, default=None, help="Max images (pilot)")
    parser.add_argument("--sleep", type=float, default=0.05, help="Seconds between API calls")
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Rewrite jsonl from scratch instead of appending new ids only",
    )
    parser.add_argument(
        "--usage-state",
        type=Path,
        default=None,
        help="Persist API usage counters (default: reports/everypixel-correlation/everypixel_usage.json)",
    )
    args = parser.parse_args()

    if args.usage_state:
        os.environ["EVERYPIXEL_USAGE_STATE_PATH"] = str(args.usage_state)
    elif not os.environ.get("EVERYPIXEL_USAGE_STATE_PATH"):
        default_state = DEFAULT_UGC_JSONL.parent / "everypixel_usage.json"
        os.environ["EVERYPIXEL_USAGE_STATE_PATH"] = str(default_state)

    if not args.manifest.is_file():
        raise SystemExit(f"Manifest not found: {args.manifest} (run export_cohort.py first)")

    fetch_ugc(
        manifest_path=args.manifest,
        out_path=args.out,
        limit=args.limit,
        sleep_sec=args.sleep,
        skip_existing=not args.no_skip_existing,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
