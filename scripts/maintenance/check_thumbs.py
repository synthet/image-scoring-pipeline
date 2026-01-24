"""
Check thumbnails utility - uses Firebird database via modules/db.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import db

try:
    conn = db.get_db()
    c = conn.cursor()
    # Firebird: Use FETCH FIRST instead of LIMIT
    c.execute("SELECT file_path, thumbnail_path FROM images WHERE file_path LIKE '%Z8%' FETCH FIRST 5 ROWS ONLY")
    rows = c.fetchall()
    print(f"Found {len(rows)} records with thumbnails.")
    for r in rows:
        print(f"File Path: {r['file_path']}")
        tp = r['thumbnail_path']
        print(f"Thumb Path: {tp}")
        print(f"Exists: {os.path.exists(tp) if tp else False}")
        if tp:
            print(f"Abs Check: {os.path.abspath(tp)}")
        
    conn.close()
except Exception as e:
    print(f"Error reading DB: {e}")
