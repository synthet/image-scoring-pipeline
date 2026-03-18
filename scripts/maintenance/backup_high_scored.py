#!/usr/bin/env python3
"""
backup_high_scored.py

Copy highly scored images from source folders to H:\\Photos, preserving folder structure.
Only copies images that meet the score threshold and that are not already at the destination.

Usage:
    python scripts/maintenance/backup_high_scored.py --source "D:\\Photos\\Z8\\180-600mm\\2026" [--dry-run]
    python scripts/maintenance/backup_high_scored.py --source "D:\\Photos" --min-score 0.8 --dry-run

Options:
    --source    Root folder to scan (required). Only images under this path are considered.
    --dest      Destination root (default: H:\\Photos)
    --min-score Minimum score_general threshold 0-1 (default: 0.72, ~4-star equivalent)
    --dry-run   Preview only, no file copies
    --yes, -y   Skip confirmation prompt

Run in WSL with app venv:
    source ~/.venvs/tf/bin/activate
    export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib
    python scripts/maintenance/backup_high_scored.py --source "D:\\Photos\\Z8\\180-600mm\\2026" --dry-run
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

# Add project root to path
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from modules.db import get_db, get_filtered_paths, init_db


def _to_wsl_path(win_path: str) -> str:
    """Convert Windows path (D:\\Photos\\...) to WSL path (/mnt/d/Photos/...)."""
    p = win_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest = p[2:].lstrip("/")
        return f"/mnt/{drive}/{rest}"
    return p


def _to_win_path(wsl_path: str) -> str:
    """Convert WSL path (/mnt/d/Photos/...) to Windows path (D:\\Photos\\...)."""
    if wsl_path.startswith("/mnt/"):
        parts = wsl_path.split("/")
        if len(parts) >= 3:
            drive = parts[2].upper()
            rest = "\\".join(parts[3:])
            return f"{drive}:\\{rest}"
    return wsl_path.replace("/", "\\")


_DB_USES_WSL: bool | None = None


def _db_uses_wsl() -> bool:
    global _DB_USES_WSL
    if _DB_USES_WSL is not None:
        return _DB_USES_WSL
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT FIRST 1 file_path FROM images")
        row = cur.fetchone()
        con.close()
        if row:
            fp = str(row[0])
            _DB_USES_WSL = fp.startswith("/mnt/")
            return _DB_USES_WSL
    except Exception:
        pass
    _DB_USES_WSL = False
    return False


def _path_to_win(path: str) -> str:
    """Convert any path to Windows format."""
    if path.startswith("/mnt/"):
        return _to_win_path(path)
    return path.replace("/", "\\")


def _path_to_wsl(path: str) -> str:
    """Convert any path to WSL format."""
    p = path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        return _to_wsl_path(path)
    return p


def _is_wsl_env() -> bool:
    """True if we're in WSL/Linux and /mnt/d exists (typical WSL setup)."""
    return sys.platform == "linux" and os.path.exists("/mnt/d")


def _resolve_for_fs(win_path: str) -> str:
    """Return path suitable for os.path.exists/shutil in current env."""
    if _is_wsl_env():
        return _to_wsl_path(win_path.replace("\\", "/"))
    return win_path.replace("/", "\\")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backup highly scored images to H:\\Photos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Root folder to scan (e.g. D:\\Photos\\Z8\\180-600mm\\2026)",
    )
    parser.add_argument(
        "--dest",
        default="H:\\Photos",
        help="Destination root (default: H:\\Photos)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.72,
        help="Minimum score_general 0-1 (default: 0.72)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no copies")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    if args.min_score < 0 or args.min_score > 1:
        print("Error: --min-score must be between 0 and 1")
        return 1

    init_db()

    # Get all highly scored image paths from DB
    paths = get_filtered_paths(min_score_general=args.min_score)
    if not paths:
        print("No images found meeting score threshold.")
        return 0

    source_win = args.source.replace("/", "\\").rstrip("\\")
    source_wsl = _to_wsl_path(source_win)
    dest_win = args.dest.replace("/", "\\").rstrip("\\")

    # Filter to paths under source
    to_copy: list[tuple[str, str, str, str]] = []  # (src_win, rel, src_fs, dest_win)
    for db_path in paths:
        db_path_str = str(db_path)
        # DB may store WSL or Windows paths
        if db_path_str.startswith("/mnt/"):
            if not db_path_str.startswith(source_wsl + "/") and db_path_str != source_wsl:
                continue
            rel = db_path_str[len(source_wsl) :].lstrip("/")
            src_win = _to_win_path(db_path_str)
        else:
            db_win = db_path_str.replace("/", "\\")
            if not db_win.lower().startswith(source_win.lower() + "\\") and db_win.lower() != source_win.lower():
                continue
            rel = db_win[len(source_win) :].lstrip("\\").replace("\\", "/")
            src_win = db_win

        if not rel:
            continue

        dest_path_win = os.path.join(dest_win, rel.replace("/", "\\"))
        dest_path_fs = _resolve_for_fs(dest_path_win)
        src_fs = _resolve_for_fs(src_win)
        if os.path.exists(dest_path_fs):
            continue  # Already backed up
        if not os.path.exists(src_fs):
            print(f"Skip (missing): {src_win}")
            continue
        to_copy.append((src_win, rel, src_fs, dest_path_win))

    if not to_copy:
        print("No new files to copy (all highly scored images already exist at destination).")
        return 0

    print(f"Found {len(to_copy)} highly scored images to copy (score_general >= {args.min_score})")
    print(f"  Source: {source_win}")
    print(f"  Dest:   {dest_win}")
    if args.dry_run:
        for item in to_copy[:20]:
            print(f"  Would copy: {item[1]}")
        if len(to_copy) > 20:
            print(f"  ... and {len(to_copy) - 20} more")
        return 0

    if not args.yes:
        resp = input("Proceed? [y/N]: ").strip().lower()
        if resp not in ("y", "yes"):
            print("Aborted.")
            return 0

    copied = 0
    errors = 0
    for src_win, rel, src_fs, dest_win_path in to_copy:
        dest_fs = _resolve_for_fs(dest_win_path)
        dest_dir = os.path.dirname(dest_fs)
        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(src_fs, dest_fs)
            copied += 1
            print(f"  Copied: {rel}")
        except Exception as e:
            errors += 1
            print(f"  Error {rel}: {e}")

    print(f"\nDone. Copied {copied} files, {errors} errors.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
