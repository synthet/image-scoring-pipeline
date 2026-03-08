#!/usr/bin/env python3
"""
Restore IMAGE_EXIF and IMAGE_XMP rows from corrupted DB into restored DB.

Copies rows that exist in corrupted but are missing in restored.
Run compare_corrupted_db.py first to confirm what will be merged.

Usage:
  python scripts/maintenance/merge_exif_xmp_from_corrupted.py [--corrupted PATH] [--restored PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_RESTORED = PROJECT_ROOT / "SCORING_HISTORY.FDB"
DEFAULT_CORRUPTED = PROJECT_ROOT / "SCORING_HISTORY.FDB.corrupted"


def get_connection(database_path: str | Path, user: str = "sysdba", password: str = "masterkey"):
    from firebird.driver import connect, driver_config

    if os.name == "nt":
        fb_dll = PROJECT_ROOT / "Firebird" / "fbclient.dll"
        if fb_dll.exists() and hasattr(driver_config, "fb_client_library"):
            driver_config.fb_client_library.value = str(fb_dll)
    else:
        fb_so = (
            PROJECT_ROOT
            / "FirebirdLinux"
            / "Firebird-5.0.0.1306-0-linux-x64"
            / "opt"
            / "firebird"
            / "lib"
            / "libfbclient.so"
        )
        if fb_so.exists() and hasattr(driver_config, "fb_client_library"):
            driver_config.fb_client_library.value = str(fb_so)

    return connect(str(Path(database_path).resolve()), user=user, password=password, charset="UTF8")


def get_missing_image_ids(conn_restored, conn_corrupted, table: str) -> list[int]:
    """Return image_ids that have rows in corrupted but not in restored."""
    cur_r = conn_restored.cursor()
    cur_c = conn_corrupted.cursor()
    try:
        cur_r.execute(f"SELECT image_id FROM {table}")
        ids_restored = {row[0] for row in cur_r.fetchall() if row[0]}
        cur_c.execute(f"SELECT image_id FROM {table}")
        missing = [row[0] for row in cur_c.fetchall() if row[0] and row[0] not in ids_restored]
        return list(dict.fromkeys(missing))  # preserve order, dedupe
    finally:
        cur_r.close()
        cur_c.close()


def get_column_names(conn, table: str) -> list[str]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT r.RDB$FIELD_NAME
            FROM RDB$RELATION_FIELDS r
            WHERE r.RDB$RELATION_NAME = ?
            ORDER BY r.RDB$FIELD_POSITION
            """,
            (table.upper(),),
        )
        return [row[0].strip() if row[0] else "" for row in cur.fetchall()]
    except Exception:
        return []
    finally:
        cur.close()


def copy_exif_rows(conn_corrupted, conn_restored, image_ids: list[int], dry_run: bool) -> int:
    if not image_ids:
        return 0
    cols = get_column_names(conn_corrupted, "IMAGE_EXIF")
    if not cols:
        return 0
    cols_str = ", ".join(cols)
    placeholders = ", ".join(["?"] * len(cols))

    cur_src = conn_corrupted.cursor()
    cur_dst = conn_restored.cursor()
    count = 0
    try:
        for img_id in image_ids:
            cur_src.execute(f"SELECT {cols_str} FROM image_exif WHERE image_id = ?", (img_id,))
            row = cur_src.fetchone()
            if not row:
                continue
            if dry_run:
                count += 1
                continue
            cur_dst.execute(
                f"INSERT INTO image_exif ({cols_str}) VALUES ({placeholders})",
                tuple(row),
            )
            count += 1
        if not dry_run and count > 0:
            conn_restored.commit()
    except Exception as e:
        if not dry_run:
            conn_restored.rollback()
        raise e
    finally:
        cur_src.close()
        cur_dst.close()
    return count


def copy_xmp_rows(conn_corrupted, conn_restored, image_ids: list[int], dry_run: bool) -> int:
    if not image_ids:
        return 0
    cols = get_column_names(conn_corrupted, "IMAGE_XMP")
    if not cols:
        return 0
    cols_str = ", ".join(cols)
    placeholders = ", ".join(["?"] * len(cols))

    cur_src = conn_corrupted.cursor()
    cur_dst = conn_restored.cursor()
    count = 0
    try:
        for img_id in image_ids:
            cur_src.execute(f"SELECT {cols_str} FROM image_xmp WHERE image_id = ?", (img_id,))
            row = cur_src.fetchone()
            if not row:
                continue
            if dry_run:
                count += 1
                continue
            cur_dst.execute(
                f"INSERT INTO image_xmp ({cols_str}) VALUES ({placeholders})",
                tuple(row),
            )
            count += 1
        if not dry_run and count > 0:
            conn_restored.commit()
    except Exception as e:
        if not dry_run:
            conn_restored.rollback()
        raise e
    finally:
        cur_src.close()
        cur_dst.close()
    return count


def main():
    ap = argparse.ArgumentParser(description="Restore IMAGE_EXIF and IMAGE_XMP from corrupted DB")
    ap.add_argument("--corrupted", default=str(DEFAULT_CORRUPTED), help="Path to corrupted .FDB")
    ap.add_argument("--restored", default=str(DEFAULT_RESTORED), help="Path to restored .FDB")
    ap.add_argument("--dry-run", action="store_true", help="Report only, do not write")
    ap.add_argument("--user", default="sysdba")
    ap.add_argument("--password", default=os.environ.get("FIREBIRD_PASSWORD", "masterkey"))
    args = ap.parse_args()

    restored_path = Path(args.restored)
    corrupted_path = Path(args.corrupted)

    if not restored_path.exists():
        print(f"ERROR: Restored DB not found: {restored_path}")
        sys.exit(1)
    if not corrupted_path.exists():
        print(f"ERROR: Corrupted DB not found: {corrupted_path}")
        sys.exit(1)

    print("NOTE: Close Web UI, Electron gallery, and any DB-using processes first.")
    print("Connecting...")
    conn_restored = get_connection(restored_path, args.user, args.password)
    conn_corrupted = get_connection(corrupted_path, args.user, args.password)

    try:
        missing_exif_ids = get_missing_image_ids(conn_restored, conn_corrupted, "image_exif")
        missing_xmp_ids = get_missing_image_ids(conn_restored, conn_corrupted, "image_xmp")

        print(f"IMAGE_EXIF rows to restore: {len(missing_exif_ids)}")
        print(f"IMAGE_XMP rows to restore: {len(missing_xmp_ids)}")

        if args.dry_run:
            print("\n[DRY RUN] No changes made.")
            return 0

        if not missing_exif_ids and not missing_xmp_ids:
            print("Nothing to restore.")
            return 0

        exif_count = copy_exif_rows(conn_corrupted, conn_restored, missing_exif_ids, dry_run=False)
        xmp_count = copy_xmp_rows(conn_corrupted, conn_restored, missing_xmp_ids, dry_run=False)

        print(f"\nRestored: {exif_count} IMAGE_EXIF, {xmp_count} IMAGE_XMP rows.")
    finally:
        conn_restored.close()
        conn_corrupted.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
