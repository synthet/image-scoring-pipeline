#!/usr/bin/env python3
"""
Unmark a folder as fully scored to allow re-scoring.

Usage:
    python scripts/unmark_folder.py --folder /mnt/d/Photos/Z8/180-600mm/2026/2026-01-25
    python scripts/unmark_folder.py --folder "D:\\Photos\\Z8\\2026"
"""
import argparse
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from modules import db


def main():
    parser = argparse.ArgumentParser(description="Unmark a folder as fully scored to allow re-scoring")
    parser.add_argument("--folder", required=True, help="Folder path to unmark")
    args = parser.parse_args()

    folder_path = args.folder
    print(f"Unmarking folder: {folder_path}")
    db.init_db()
    db.set_folder_scored(folder_path, is_scored=False)
    print("Done! Folder is now unmarked and will be re-scored.")


if __name__ == "__main__":
    main()
