#!/usr/bin/env python3
"""List all unique keywords used in the database."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.db import get_db

def main():
    conn = get_db()
    cur = conn.cursor()
    seen = set()

    # IMAGES.keywords - can be comma-separated or JSON
    cur.execute("SELECT keywords FROM images WHERE keywords IS NOT NULL AND keywords != ''")
    for row in cur.fetchall():
        val = row[0]
        if not val:
            continue
        val = str(val).strip()
        if val.startswith("["):
            try:
                kw_list = json.loads(val)
                if isinstance(kw_list, list):
                    for k in kw_list:
                        if k and isinstance(k, str):
                            seen.add(k.strip())
            except json.JSONDecodeError:
                for k in val.split(","):
                    k = k.strip().strip('"')
                    if k:
                        seen.add(k)
        else:
            for k in val.split(","):
                k = k.strip().strip('"')
                if k:
                    seen.add(k)

    # IMAGE_XMP.keywords - JSON array
    cur.execute("SELECT keywords FROM image_xmp WHERE keywords IS NOT NULL AND keywords != ''")
    for row in cur.fetchall():
        val = row[0]
        if not val:
            continue
        try:
            kw_list = json.loads(str(val))
            if isinstance(kw_list, list):
                for k in kw_list:
                    if k and isinstance(k, str):
                        seen.add(k.strip())
        except (json.JSONDecodeError, TypeError):
            pass

    keywords = sorted(seen)
    print(f"Total unique keywords: {len(keywords)}")
    for kw in keywords:
        print(kw)

if __name__ == "__main__":
    main()
