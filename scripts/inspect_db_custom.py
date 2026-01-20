import sqlite3
import os

db_path = "scoring_history.db"

if not os.path.exists(db_path):
    print(f"Error: {db_path} not found")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

try:
    c.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = c.fetchall()
    print("Tables:", [t[0] for t in tables])

    c.execute("SELECT id, file_path, created_at FROM images LIMIT 5")
    rows = c.fetchall()
    print("\nSample Rows:")
    for row in rows:
        print(row)
except Exception as e:
    print(f"Error reading DB: {e}")
finally:
    conn.close()
