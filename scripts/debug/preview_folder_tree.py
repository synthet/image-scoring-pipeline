#!/usr/bin/env python3
"""
Load folders from the DB and print a small preview of the ui_tree hierarchy.

Usage (WSL, venv + DB per CLAUDE.md):
  python scripts/debug/preview_folder_tree.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from modules import db, ui_tree

    folders = db.get_all_folders()
    print(f"Total folders from DB: {len(folders)}")

    filtered = [p for p in folders if p and p not in ("/", "/mnt", "/mnt/d")]
    print(f"Filtered folders: {len(filtered)}")

    roots = ui_tree.build_tree_dict(filtered)
    print(f"Roots count: {len(roots)}")

    def print_tree(nodes, depth: int = 0) -> None:
        for node in nodes[:3]:
            print("  " * depth + f"- {node['name']} ({node['path']})")
            if node["children"]:
                print_tree(node["children"], depth + 1)
        if len(nodes) > 3:
            print("  " * depth + f"... ({len(nodes) - 3} more)")

    print("\nTree structure preview:")
    print_tree(roots)
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)
