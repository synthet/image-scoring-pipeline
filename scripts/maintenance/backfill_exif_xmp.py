#!/usr/bin/env python3
"""
Backfill EXIF and XMP metadata into IMAGE_EXIF and IMAGE_XMP tables.

Iterates over images in the database, extracts EXIF via exiftool and XMP from
sidecars, and upserts into the cache tables. Use for existing images that were
scored before metadata caching was added.

Run in WSL with ~/.venvs/tf (same env as the webapp).
Use: scripts/maintenance/run_backfill_exif_xmp.bat (from Windows)
     or: wsl + source ~/.venvs/tf/bin/activate + python scripts/maintenance/backfill_exif_xmp.py

Troubleshooting Firebird "file in use" error:
- Ensure Firebird server is running on Windows (port 3050).
- Close WebUI and any other process that may have the DB open.
- If DB doesn't exist, run migrate_to_firebird.py first.
"""
import sys
import os
import argparse
import logging
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules import db, utils
from modules.exif_extractor import extract_and_upsert_exif
from modules.xmp import extract_and_upsert_xmp

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill EXIF and XMP metadata into IMAGE_EXIF and IMAGE_XMP tables"
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=None,
        help="Restrict to images in this folder path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of images to process",
    )
    parser.add_argument(
        "--exif-only",
        action="store_true",
        help="Only backfill EXIF, skip XMP",
    )
    parser.add_argument(
        "--xmp-only",
        action="store_true",
        help="Only backfill XMP, skip EXIF",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report count and paths only, do not write to DB",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all images. By default only images without cached EXIF/XMP are processed.",
    )
    args = parser.parse_args()

    if args.exif_only and args.xmp_only:
        parser.error("--exif-only and --xmp-only are mutually exclusive")

    db.init_db()

    conn = db.get_db()
    c = conn.cursor()

    # Base: images in DB
    query = "SELECT i.id, i.file_path FROM images i"
    where_parts = []
    params = []
    if not args.all:
        # Only images without cached EXIF/XMP
        if not args.xmp_only:
            where_parts.append("NOT EXISTS (SELECT 1 FROM image_exif e WHERE e.image_id = i.id)")
        if not args.exif_only:
            where_parts.append("NOT EXISTS (SELECT 1 FROM image_xmp x WHERE x.image_id = i.id)")
    if args.folder:
        folder_id = db.get_or_create_folder(args.folder)
        if not folder_id:
            logger.error("Folder not found or could not be created: %s", args.folder)
            sys.exit(1)
        where_parts.append("i.folder_id = ?")
        params.append(folder_id)
    if where_parts:
        query += " WHERE " + " AND ".join(where_parts)
    query += " ORDER BY i.id"

    c.execute(query, tuple(params))
    rows = c.fetchall()
    conn.close()

    total = len(rows)
    if args.limit:
        rows = rows[: args.limit]
    to_process = len(rows)

    logger.info("Found %d images to process (limit=%s, uncached_only=%s)", to_process, args.limit or "none", not args.all)

    if to_process == 0:
        logger.info("No images to process.")
        return

    if args.dry_run:
        for i, row in enumerate(rows[:10]):
            logger.info("  %s", row.get("file_path", row[1]))
        if to_process > 10:
            logger.info("  ... and %d more", to_process - 10)
        return

    exif_ok = 0
    exif_fail = 0
    xmp_ok = 0
    xmp_skip = 0

    for i, row in enumerate(rows):
        img_id = row["id"] if "id" in row.keys() else row[0]
        file_path = row["file_path"] if "file_path" in row.keys() else row[1]

        if not file_path:
            continue

        if not args.xmp_only:
            if extract_and_upsert_exif(file_path, img_id):
                exif_ok += 1
            else:
                exif_fail += 1
                logger.debug("EXIF extraction failed: %s", file_path)

        if not args.exif_only:
            if extract_and_upsert_xmp(file_path, img_id):
                xmp_ok += 1
            else:
                xmp_skip += 1  # No XMP sidecar is normal

        if (i + 1) % 50 == 0:
            logger.info("Progress: %d/%d", i + 1, to_process)

    logger.info("Backfill complete. EXIF: %d ok, %d fail. XMP: %d ok, %d no sidecar", exif_ok, exif_fail, xmp_ok, xmp_skip)


if __name__ == "__main__":
    main()
