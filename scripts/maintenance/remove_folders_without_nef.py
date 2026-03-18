#!/usr/bin/env python3
"""
remove_folders_without_nef.py

Remove folders under a root path that contain no Nikon RAW (.NEF) files.
Useful for cleaning H:\\Photos after backup_high_scored.py — keep only folders
that have at least one NEF file (or a subfolder with NEFs).

Usage:
    python scripts/maintenance/remove_folders_without_nef.py --root "H:\\Photos" [--dry-run]
    python scripts/maintenance/remove_folders_without_nef.py --root "H:\\Photos" --yes

Options:
    --root      Root folder to scan (default: H:\\Photos)
    --dry-run   Preview only, no deletions
    --yes, -y   Skip confirmation prompt
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

NEF_EXT = ".nef"


def _has_nef_files(dir_path: Path) -> bool:
    """Check if this directory or any descendant contains .NEF files."""
    try:
        for root, _, files in os.walk(dir_path):
            for f in files:
                if f.lower().endswith(NEF_EXT):
                    return True
    except OSError:
        pass
    return False


def _collect_empty_folders(root: Path) -> list[Path]:
    """Return folders (and their subfolders) that contain no NEF files, deepest first."""
    to_remove: list[Path] = []
    try:
        for dirpath, dirnames, _ in os.walk(root, topdown=False):
            dir_path = Path(dirpath)
            if dir_path == root:
                continue
            if not _has_nef_files(dir_path):
                to_remove.append(dir_path)
    except OSError as e:
        print(f"Error walking {root}: {e}", file=sys.stderr)
        sys.exit(1)
    return to_remove


def main() -> None:
    ap = argparse.ArgumentParser(description="Remove folders without Nikon RAW (.NEF) files")
    ap.add_argument("--root", default=r"H:\Photos", help="Root folder to scan")
    ap.add_argument("--dry-run", action="store_true", help="Preview only, no deletions")
    ap.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {root} for folders without .NEF files...")
    to_remove = _collect_empty_folders(root)
    to_remove.sort(key=lambda p: len(p.parts), reverse=True)

    if not to_remove:
        print("No folders to remove.")
        return

    print(f"\nFound {len(to_remove)} folder(s) without NEF files:")
    for p in to_remove[:50]:
        print(f"  {p}")
    if len(to_remove) > 50:
        print(f"  ... and {len(to_remove) - 50} more")

    if args.dry_run:
        print("\n[DRY RUN] No folders removed.")
        return

    if not args.yes:
        reply = input("\nRemove these folders? [y/N]: ").strip().lower()
        if reply not in ("y", "yes"):
            print("Aborted.")
            return

    removed = 0
    for dir_path in to_remove:
        if not dir_path.exists():
            continue
        try:
            shutil.rmtree(dir_path)
            print(f"Removed: {dir_path}")
            removed += 1
        except OSError as e:
            print(f"Failed to remove {dir_path}: {e}", file=sys.stderr)

    print(f"\nRemoved {removed} folder(s).")


if __name__ == "__main__":
    main()
