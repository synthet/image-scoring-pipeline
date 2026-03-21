#!/usr/bin/env python3
"""
Enqueue one tagging job per folder that has images with no keywords (DB view).

Uses db.list_folder_paths_with_missing_keywords and resolve_selectors (same as
POST /api/tagging/start) so queue_payload contains resolved_image_ids.

Usage (WSL, project root, venv per CLAUDE.md):
  export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib
  source ~/.venvs/tf/bin/activate
  python scripts/wsl/enqueue_untagged_folder_tagging.py --dry-run

  python scripts/wsl/enqueue_untagged_folder_tagging.py --limit 10
  python scripts/wsl/enqueue_untagged_folder_tagging.py --require-embedding --overwrite

Requires WebUI / JobDispatcher running for queued jobs to execute.
Images marked keywords phase done but empty keywords need --overwrite to re-run.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _enqueue_one_folder(
    folder_path: str,
    *,
    overwrite: bool,
    generate_captions: bool,
    custom_keywords: list[str] | None,
) -> tuple[int | None, int]:
    from modules import db
    from modules.selector_resolver import resolve_selectors

    sel = resolve_selectors(
        folder_paths=[folder_path],
        recursive=False,
        index_missing=True,
    )
    resolved_ids = sel.get("resolved_image_ids") or []
    if not resolved_ids:
        logger.warning("No images resolved for folder (skipped): %s", folder_path)
        return None, 0

    job_id, queue_position = db.enqueue_job(
        folder_path,
        phase_code="keywords",
        job_type="tagging",
        queue_payload={
            "input_path": None,
            "custom_keywords": custom_keywords,
            "overwrite": overwrite,
            "generate_captions": generate_captions,
            "resolved_image_ids": resolved_ids,
        },
    )
    if job_id is None:
        logger.error("enqueue_job failed for %s", folder_path)
        return None, len(resolved_ids)

    db.create_job_phases(job_id, ["keywords"], first_phase_state="queued")
    logger.info(
        "Queued job_id=%s position=%s folder=%s images=%s",
        job_id,
        queue_position,
        folder_path,
        len(resolved_ids),
    )
    return job_id, len(resolved_ids)


def main() -> int:
    from modules import db

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="List folders only; do not enqueue")
    p.add_argument(
        "--require-embedding",
        action="store_true",
        help="Only folders where untagged images have image_embedding (propagation-aligned)",
    )
    p.add_argument("--overwrite", action="store_true", help="Force tagging even if keywords phase is done")
    p.add_argument(
        "--generate-captions",
        action="store_true",
        help="Pass generate_captions=true in job payload (heavier)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Enqueue at most N folders (0 = no limit)",
    )
    p.add_argument(
        "--output-json",
        type=str,
        default="",
        help="Write folder list [{path, untagged_count}, ...] to this file",
    )
    args = p.parse_args()

    rows = db.list_folder_paths_with_missing_keywords(require_embedding=args.require_embedding)
    if args.output_json:
        payload = [{"path": path, "untagged_count": n} for path, n in rows]
        out_path = os.path.abspath(args.output_json)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logger.info("Wrote %s folders to %s", len(payload), out_path)

    if not rows:
        logger.info("No folders with missing keywords.")
        return 0

    logger.info("Found %s folder(s) with at least one image without keywords", len(rows))

    if args.dry_run:
        cap = args.limit if args.limit and args.limit > 0 else None
        slice_rows = rows[:cap] if cap is not None else rows
        for path, n in slice_rows[:20]:
            logger.info("  %s  (%s images)", path, n)
        if len(slice_rows) > 20:
            logger.info("  ... and %s more", len(slice_rows) - 20)
        return 0

    limit = args.limit if args.limit and args.limit > 0 else len(rows)
    enqueued = 0
    for path, n in rows:
        if enqueued >= limit:
            break
        job_id, _ = _enqueue_one_folder(
            path,
            overwrite=args.overwrite,
            generate_captions=args.generate_captions,
            custom_keywords=None,
        )
        if job_id is not None:
            enqueued += 1

    logger.info("Enqueued %s tagging job(s)", enqueued)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
