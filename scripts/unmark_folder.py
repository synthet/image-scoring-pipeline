#!/usr/bin/env python3
"""
Unmark a folder as fully scored to allow re-scoring.
"""
import sys
sys.path.insert(0, 'd:/Projects/image-scoring')

from modules import db

folder_path = "/mnt/d/Photos/Z8/180-600mm/2026/2026-01-25"

print(f"Unmarking folder: {folder_path}")
db.set_folder_scored(folder_path, is_scored=False)
print("✅ Done! Folder is now unmarked and will be re-scored.")
