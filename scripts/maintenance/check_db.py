import sqlite3
import os

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../scoring_history.db"))

if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
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
