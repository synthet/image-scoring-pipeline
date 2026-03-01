#!/usr/bin/env python3
"""
Migrate thumbnails from flat layout to nested 2-char prefix subdirectories
and populate the thumbnail_path_win column.

Layout change:
  thumbnails/{hash}.jpg  -->  thumbnails/{hash[:2]}/{hash}.jpg

Run in WSL with the app venv:
  source ~/.venvs/tf/bin/activate
  python scripts/maintenance/migrate_thumbnails.py
"""

import os
import sys
import shutil
import logging
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from modules import db
from modules.thumbnails import (
    THUMB_DIR,
    thumb_path_to_win,
    thumb_path_to_wsl,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
log = logging.getLogger(__name__)


def migrate_files(dry_run=False):
    """Move flat thumbnails into nested {hash[:2]}/ subdirectories."""
    moved = 0
    skipped = 0
    errors = 0

    if not os.path.isdir(THUMB_DIR):
        log.warning("Thumbnail directory does not exist: %s", THUMB_DIR)
        return moved, skipped, errors

    for fname in os.listdir(THUMB_DIR):
        fpath = os.path.join(THUMB_DIR, fname)
        if not os.path.isfile(fpath) or not fname.endswith('.jpg'):
            continue

        stem = fname[:-4]  # strip .jpg
        if len(stem) != 32:
            skipped += 1
            continue

        prefix = stem[:2]
        target_dir = os.path.join(THUMB_DIR, prefix)
        target_path = os.path.join(target_dir, fname)

        if os.path.exists(target_path):
            skipped += 1
            continue

        try:
            if not dry_run:
                os.makedirs(target_dir, exist_ok=True)
                shutil.move(fpath, target_path)
            moved += 1
        except Exception as e:
            log.error("Failed to move %s -> %s: %s", fpath, target_path, e)
            errors += 1

    return moved, skipped, errors


def update_db_paths(dry_run=False):
    """
    For every image row, rewrite thumbnail_path to the nested layout
    and populate thumbnail_path_win.
    """
    db.init_db()
    conn = db.get_db()
    c = conn.cursor()

    c.execute("SELECT id, thumbnail_path, thumbnail_path_win FROM images")
    rows = c.fetchall()

    updated = 0
    already_ok = 0
    errors = 0

    for row in rows:
        image_id = row[0]
        tp = row[1]
        tp_win = row[2]

        if not tp:
            continue

        new_tp = _rewrite_to_nested(tp)
        new_tp_win = thumb_path_to_win(new_tp) if new_tp else tp_win

        needs_update = (new_tp != tp) or (new_tp_win != tp_win)
        if not needs_update:
            already_ok += 1
            continue

        try:
            if not dry_run:
                c.execute(
                    "UPDATE images SET thumbnail_path = ?, thumbnail_path_win = ? WHERE id = ?",
                    (new_tp, new_tp_win, image_id),
                )
            updated += 1
        except Exception as e:
            log.error("Failed to update image %s: %s", image_id, e)
            errors += 1

    if not dry_run:
        conn.commit()
    conn.close()
    return updated, already_ok, errors


def _rewrite_to_nested(path):
    """
    Rewrite a thumbnail path to the nested layout.
    /mnt/d/.../thumbnails/abc123...def.jpg  ->  /mnt/d/.../thumbnails/ab/abc123...def.jpg
    D:\\...\\thumbnails\\abc123...def.jpg     ->  D:\\...\\thumbnails\\ab\\abc123...def.jpg
    """
    norm = path.replace('\\', '/')
    parts = norm.rsplit('/', 1)
    if len(parts) != 2:
        return path

    parent, fname = parts
    stem = fname.replace('.jpg', '').replace('.JPG', '')
    if len(stem) != 32:
        return path

    prefix = stem[:2]

    # Check if already nested (parent ends with the 2-char prefix)
    if parent.endswith('/' + prefix) or parent.endswith('\\' + prefix):
        return path

    sep = '\\' if '\\' in path and '/' not in path else '/'
    return f"{parent}{sep}{prefix}{sep}{fname}"


def main():
    parser = argparse.ArgumentParser(description="Migrate thumbnails to nested directory layout")
    parser.add_argument('--dry-run', action='store_true', help="Preview changes without modifying anything")
    args = parser.parse_args()

    if args.dry_run:
        log.info("=== DRY RUN MODE (no changes will be made) ===")

    log.info("Step 1/2: Moving thumbnail files to nested directories...")
    moved, skipped, file_errors = migrate_files(dry_run=args.dry_run)
    log.info("  Files moved: %d, skipped: %d, errors: %d", moved, skipped, file_errors)

    log.info("Step 2/2: Updating database paths...")
    updated, already_ok, db_errors = update_db_paths(dry_run=args.dry_run)
    log.info("  DB rows updated: %d, already OK: %d, errors: %d", updated, already_ok, db_errors)

    log.info("Migration complete.")
    if file_errors or db_errors:
        log.warning("There were errors - review the log above.")
        sys.exit(1)


if __name__ == '__main__':
    main()
