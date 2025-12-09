import sqlite3
import os

if os.path.exists("scoring_history.db"):
    try:
        conn = sqlite3.connect("scoring_history.db")
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT file_path, thumbnail_path FROM images WHERE thumbnail_path IS NOT NULL LIMIT 5")
        rows = c.fetchall()
        print(f"Found {len(rows)} records with thumbnails.")
        for r in rows:
            tp = r['thumbnail_path']
            print(f"Thumb Path: {tp}")
            print(f"Exists: {os.path.exists(tp)}")
            print(f"Abs Check: {os.path.abspath(tp)}")
            
        conn.close()
    except Exception as e:
        print(f"Error reading DB: {e}")
else:
    print("scoring_history.db not found")
