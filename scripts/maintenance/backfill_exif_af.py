#!/usr/bin/env python3
"""Re-extract Nikon autofocus geometry into image_exif.af_metadata for rows cached before migration 0044 (#726)."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules import db  # noqa: E402
from modules.exif_extractor import (  # noqa: E402
    backfill_af_metadata,
    exiftool_supports_af,
    get_exiftool_version,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(
        description=(
            "Backfill image_exif.af_metadata from exiftool for rows where it is NULL. "
            "Reads files only; merges into the cached EXIF row. Rows the camera recorded "
            "no AF coordinates for stay NULL."
        )
    )
    p.add_argument("--limit", type=int, default=2000, help="Rows per batch (default 2000)")
    p.add_argument("--once", action="store_true", help="Single batch only")
    p.add_argument("--after-id", type=int, default=0, help="Resume after this images.id")
    p.add_argument(
        "--model-like",
        default="NIKON Z%",
        help="SQL LIKE on image_exif.model (default 'NIKON Z%%'); use --all-models to drop the filter",
    )
    p.add_argument("--all-models", action="store_true", help="Do not filter by camera model")
    p.add_argument("--path-like", metavar="PATTERN", help=r"Optional SQL LIKE on images.file_path (e.g. %%/2026-10-24/%%)")
    p.add_argument(
        "--allow-old-exiftool",
        action="store_true",
        help="Run even when exiftool < 13 (Z8 AF geometry will not decode)",
    )
    args = p.parse_args()

    version = get_exiftool_version()
    if not exiftool_supports_af() and not args.allow_old_exiftool:
        logger.error(
            "exiftool %s cannot decode Nikon Z AF geometry; need 13.x (see Dockerfile pin). "
            "Run in the gpu-shell/Docker image or pass --allow-old-exiftool.",
            version,
        )
        sys.exit(2)
    logger.info("exiftool %s", version)

    db.init_db()
    model_like = None if args.all_models else args.model_like
    after_id = args.after_id
    grand = {"checked": 0, "updated": 0, "no_af": 0, "skipped_no_file": 0, "skipped_no_exif": 0, "errors": 0}
    while True:
        stats = backfill_af_metadata(
            limit=args.limit,
            after_id=after_id,
            model_like=model_like,
            path_like=args.path_like,
        )
        for k in grand:
            grand[k] += stats[k]
        after_id = stats["last_id"]
        logger.info("batch %s | cumulative %s | resume with --after-id %s", stats, grand, after_id)
        if args.once or stats["checked"] == 0:
            break
    logger.info("finished %s", grand)


if __name__ == "__main__":
    main()
