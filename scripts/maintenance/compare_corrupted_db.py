#!/usr/bin/env python3
r"""
Compare corrupted Firebird DB with restored backup to identify recoverable data.

Usage:
  python scripts/maintenance/compare_corrupted_db.py [--corrupted PATH] [--restored PATH] [--export PATH]

The script:
  1. Attempts to connect to both databases
  2. Compares IMAGES (by image_hash), FOLDERS (by path), JOBS, and related tables
  3. Reports what exists in corrupted but is missing in restored
  4. Optionally exports missing rows to JSON for manual merge

If the corrupted file won't connect, try Firebird's gfix first:
  gfix -mend -user sysdba -password masterkey "D:\Projects\image-scoring\SCORING_HISTORY.FDB.corrupted"
  gbak -b -g -user sysdba -password masterkey "D:\...\SCORING_HISTORY.FDB.corrupted" backup.fbk
  gbak -c -user sysdba -password masterkey backup.fbk "D:\...\recovered.FDB"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Project root
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Default paths
DEFAULT_RESTORED = PROJECT_ROOT / "SCORING_HISTORY.FDB"
DEFAULT_CORRUPTED = PROJECT_ROOT / "SCORING_HISTORY.FDB.corrupted"


def get_connection(database_path: str | Path, user: str = "sysdba", password: str = "masterkey"):
    """Connect to a Firebird database. Uses same driver config as modules.db."""
    from firebird.driver import connect, driver_config

    # Ensure client library is set (same as db.py)
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

    path = str(Path(database_path).resolve())
    # On WSL, may need inet:// - for now assume local/embedded works when path exists
    return connect(path, user=user, password=password, charset="UTF8")


def fetch_table(conn, table: str, columns: list[str] | None = None) -> list[tuple]:
    """Fetch all rows from a table. Returns list of tuples."""
    cols = ", ".join(columns) if columns else "*"
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT {cols} FROM {table}")
        return cur.fetchall()
    except Exception as e:
        return []  # Table might not exist or be corrupted
    finally:
        cur.close()


def get_column_names(conn, table: str) -> list[str]:
    """Get column names for a table."""
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


def row_to_dict(columns: list[str], row: tuple) -> dict:
    """Convert row tuple to dict. Handle BLOB/bytes."""
    d = {}
    for i, col in enumerate(columns):
        if i >= len(row):
            break
        v = row[i]
        if isinstance(v, bytes):
            try:
                v = v.decode("utf-8", errors="replace")
            except Exception:
                v = "<binary>"
        d[col] = v
    return d


def compare_images(conn_restored, conn_corrupted) -> tuple[list[dict], set[str]]:
    """Compare IMAGES by image_hash. Return (missing_in_restored, hashes_in_restored)."""
    cols = get_column_names(conn_restored, "IMAGES")
    if not cols:
        return [], set()

    cur_r = conn_restored.cursor()
    cur_c = conn_corrupted.cursor()
    try:
        cur_r.execute("SELECT image_hash FROM images WHERE image_hash IS NOT NULL")
        hashes_restored = {row[0] for row in cur_r.fetchall() if row[0]}

        cur_c.execute("SELECT * FROM images")
        rows_c = cur_c.fetchall()
        missing = []
        for row in rows_c:
            row_dict = row_to_dict(cols, row)
            h = row_dict.get("IMAGE_HASH") or row_dict.get("image_hash")
            if h and h not in hashes_restored:
                missing.append(row_dict)
        return missing, hashes_restored
    finally:
        cur_r.close()
        cur_c.close()


def compare_folders(conn_restored, conn_corrupted) -> list[dict]:
    """Compare FOLDERS by path. Return folders in corrupted missing in restored."""
    cur_r = conn_restored.cursor()
    cur_c = conn_corrupted.cursor()
    try:
        cur_r.execute("SELECT path FROM folders")
        paths_restored = {row[0] for row in cur_r.fetchall() if row[0]}

        cols = get_column_names(conn_corrupted, "FOLDERS")
        cur_c.execute("SELECT * FROM folders")
        missing = []
        for row in cur_c.fetchall():
            d = row_to_dict(cols, row)
            p = d.get("PATH") or d.get("path")
            if p and p not in paths_restored:
                missing.append(d)
        return missing
    finally:
        cur_r.close()
        cur_c.close()


def compare_jobs(conn_restored, conn_corrupted) -> list[dict]:
    """Compare JOBS. Use (input_path, created_at) as key."""
    cur_r = conn_restored.cursor()
    cur_c = conn_corrupted.cursor()
    try:
        cur_r.execute("SELECT input_path, created_at FROM jobs")
        keys_restored = {(row[0] or "", str(row[1]) if row[1] else "") for row in cur_r.fetchall()}

        cols = get_column_names(conn_corrupted, "JOBS")
        cur_c.execute("SELECT * FROM jobs")
        missing = []
        for row in cur_c.fetchall():
            d = row_to_dict(cols, row)
            key = (d.get("INPUT_PATH") or d.get("input_path") or "", str(d.get("CREATED_AT") or d.get("created_at") or ""))
            if key not in keys_restored:
                missing.append(d)
        return missing
    finally:
        cur_r.close()
        cur_c.close()


def compare_stacks(conn_restored, conn_corrupted) -> list[dict]:
    """Compare STACKS by name (or id if name empty)."""
    cur_r = conn_restored.cursor()
    cur_c = conn_corrupted.cursor()
    try:
        cur_r.execute("SELECT id, name FROM stacks")
        keys_restored = {(row[0], row[1] or "") for row in cur_r.fetchall()}

        cols = get_column_names(conn_corrupted, "STACKS")
        cur_c.execute("SELECT * FROM stacks")
        missing = []
        for row in cur_c.fetchall():
            d = row_to_dict(cols, row)
            sid = d.get("ID") or d.get("id")
            sname = d.get("NAME") or d.get("name") or ""
            if (sid, sname) not in keys_restored:
                missing.append(d)
        return missing
    finally:
        cur_r.close()
        cur_c.close()


def compare_image_exif(conn_restored, conn_corrupted) -> list[dict]:
    """Compare IMAGE_EXIF by image_id. Rows in corrupted missing in restored."""
    cur_r = conn_restored.cursor()
    cur_c = conn_corrupted.cursor()
    try:
        cur_r.execute("SELECT image_id FROM image_exif")
        ids_restored = {row[0] for row in cur_r.fetchall() if row[0]}

        cols = get_column_names(conn_corrupted, "IMAGE_EXIF")
        if not cols:
            return []
        cur_c.execute("SELECT * FROM image_exif")
        missing = []
        for row in cur_c.fetchall():
            d = row_to_dict(cols, row)
            img_id = d.get("IMAGE_ID") or d.get("image_id")
            if img_id and img_id not in ids_restored:
                missing.append(d)
        return missing
    except Exception:
        return []
    finally:
        cur_r.close()
        cur_c.close()


def compare_image_xmp(conn_restored, conn_corrupted) -> list[dict]:
    """Compare IMAGE_XMP by image_id. Rows in corrupted missing in restored."""
    cur_r = conn_restored.cursor()
    cur_c = conn_corrupted.cursor()
    try:
        cur_r.execute("SELECT image_id FROM image_xmp")
        ids_restored = {row[0] for row in cur_r.fetchall() if row[0]}

        cols = get_column_names(conn_corrupted, "IMAGE_XMP")
        if not cols:
            return []
        cur_c.execute("SELECT * FROM image_xmp")
        missing = []
        for row in cur_c.fetchall():
            d = row_to_dict(cols, row)
            img_id = d.get("IMAGE_ID") or d.get("image_id")
            if img_id and img_id not in ids_restored:
                missing.append(d)
        return missing
    except Exception:
        return []
    finally:
        cur_r.close()
        cur_c.close()


def main():
    ap = argparse.ArgumentParser(description="Compare corrupted vs restored Firebird DB")
    ap.add_argument("--corrupted", default=str(DEFAULT_CORRUPTED), help="Path to corrupted .FDB")
    ap.add_argument("--restored", default=str(DEFAULT_RESTORED), help="Path to restored .FDB")
    ap.add_argument("--export", metavar="PATH", help="Export missing data to JSON file")
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
    print("Connecting to restored database...")
    try:
        conn_restored = get_connection(restored_path, args.user, args.password)
        print("  OK")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    print("Connecting to corrupted database...")
    try:
        conn_corrupted = get_connection(corrupted_path, args.user, args.password)
        print("  OK")
    except Exception as e:
        print(f"  FAILED: {e}")
        print("\nThe corrupted file may be unreadable. Try Firebird recovery first:")
        print(f'  gfix -mend -user {args.user} -password **** "{corrupted_path}"')
        print('  gbak -b -g -user sysdba -password masterkey "corrupted.FDB.corrupted" backup.fbk')
        print('  gbak -c -user sysdba -password masterkey backup.fbk recovered.FDB')
        conn_restored.close()
        sys.exit(1)

    results = {}

    try:
        # Compare IMAGES (primary recoverable data)
        print("\nComparing IMAGES (by image_hash)...")
        missing_images, _ = compare_images(conn_restored, conn_corrupted)
        results["images_missing_in_restored"] = missing_images
        print(f"  Images in corrupted but NOT in restored: {len(missing_images)}")

        # Compare FOLDERS
        print("\nComparing FOLDERS...")
        missing_folders = compare_folders(conn_restored, conn_corrupted)
        results["folders_missing_in_restored"] = missing_folders
        print(f"  Folders in corrupted but NOT in restored: {len(missing_folders)}")

        # Compare JOBS
        print("\nComparing JOBS...")
        missing_jobs = compare_jobs(conn_restored, conn_corrupted)
        results["jobs_missing_in_restored"] = missing_jobs
        print(f"  Jobs in corrupted but NOT in restored: {len(missing_jobs)}")

        # Compare STACKS
        print("\nComparing STACKS...")
        missing_stacks = compare_stacks(conn_restored, conn_corrupted)
        results["stacks_missing_in_restored"] = missing_stacks
        print(f"  Stacks in corrupted but NOT in restored: {len(missing_stacks)}")

        # Compare IMAGE_EXIF
        print("\nComparing IMAGE_EXIF...")
        missing_exif = compare_image_exif(conn_restored, conn_corrupted)
        results["image_exif_missing_in_restored"] = missing_exif
        print(f"  IMAGE_EXIF rows in corrupted but NOT in restored: {len(missing_exif)}")

        # Compare IMAGE_XMP
        print("\nComparing IMAGE_XMP...")
        missing_xmp = compare_image_xmp(conn_restored, conn_corrupted)
        results["image_xmp_missing_in_restored"] = missing_xmp
        print(f"  IMAGE_XMP rows in corrupted but NOT in restored: {len(missing_xmp)}")

        # Summary
        total_recoverable = (
            len(missing_images) + len(missing_folders) + len(missing_jobs)
            + len(missing_stacks) + len(missing_exif) + len(missing_xmp)
        )
        print("\n" + "=" * 60)
        print(f"TOTAL recoverable records (in corrupted, missing in restored): {total_recoverable}")
        if missing_images:
            print(f"\n  IMAGES: {len(missing_images)} rows (scores, metadata, ratings, labels)")
            sample_paths = [m.get("FILE_PATH") or m.get("file_path") for m in missing_images[:3]]
            for p in sample_paths:
                if p:
                    print(f"    e.g. {str(p)[:80]}...")
        if missing_folders:
            print(f"\n  FOLDERS: {len(missing_folders)} (folder hierarchy)")
        if missing_jobs:
            print(f"\n  JOBS: {len(missing_jobs)} (scoring job history)")
        if missing_stacks:
            print(f"\n  STACKS: {len(missing_stacks)} (image clusters)")
        if missing_exif:
            print(f"\n  IMAGE_EXIF: {len(missing_exif)} (cached EXIF: make, model, lens, ISO, etc.)")
        if missing_xmp:
            print(f"\n  IMAGE_XMP: {len(missing_xmp)} (cached XMP: ratings, labels, burst/stack IDs)")

        # Export if requested
        if args.export and total_recoverable > 0:
            out_path = Path(args.export)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, default=str)
            print(f"\nExported to {out_path}")

    finally:
        conn_restored.close()
        conn_corrupted.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
