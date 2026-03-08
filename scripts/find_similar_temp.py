#!/usr/bin/env python
"""Find images similar to a given file path."""
import sys
import os
# Ensure project root is on path when run from scripts/
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
from modules import db, similar_search

def main():
    target = "DSC_2123.jpg"
    # Try multiple path formats (DB stores WSL paths like /mnt/d/Photos/...)
    paths_to_try = [
        "/mnt/d/Photos/Export/2025/DSC_2123.jpg",
        r"D:\Photos\Export\2025\DSC_2123.jpg",
        "D:/Photos/Export/2025/DSC_2123.jpg",
    ]
    conn = db.get_db()
    c = conn.cursor()
    # First try exact path match
    for p in paths_to_try:
        c.execute("SELECT id, file_path FROM images WHERE file_path = ?", (p,))
        row = c.fetchone()
        if row:
            rows = [row]
            break
    else:
        # Fallback: search by filename
        c.execute(
            "SELECT id, file_path FROM images WHERE file_name LIKE ? OR file_path LIKE ?",
            (f"%{target}%", f"%{target}%"),
        )
        rows = c.fetchall()
    conn.close()

    if not rows:
        print("Image not found in database.")
        conn = db.get_db()
        c = conn.cursor()
        c.execute("SELECT FIRST 5 file_path FROM images")
        samples = c.fetchall()
        conn.close()
        print("Sample paths in DB:", [s[0] for s in samples])
        return 1

    for r in rows:
        print(f"Found: id={r[0]}, path={r[1]}")
    example_path = rows[0][1]

    result = similar_search.search_similar_images(
        example_path=example_path, limit=15, min_similarity=0.7
    )
    if isinstance(result, dict) and "error" in result:
        print("Error:", result["error"])
        return 1

    print()
    print("Similar images (sorted by similarity):")
    for i, r in enumerate(result, 1):
        print(f"  {i}. {r['similarity']:.1%} - {r['file_path']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
