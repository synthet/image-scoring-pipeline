import sqlite3
import os

if os.path.exists("scoring_history.db"):
    try:
        conn = sqlite3.connect("scoring_history.db")
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM images")
        count = c.fetchone()[0]
        print(f"Total images in DB: {count}")
        
        c.execute("SELECT * FROM images LIMIT 5")
        rows = c.fetchall()
        print("First 5 records:")
        for r in rows:
            print(r)
            
        conn.close()
    except Exception as e:
        print(f"Error reading DB: {e}")
else:
    print("scoring_history.db not found")
