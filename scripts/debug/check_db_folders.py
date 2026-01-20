
import sqlite3
import os

db_path = 'scoring_history.db'
if not os.path.exists(db_path):
    print("DB not found")
    exit()

conn = sqlite3.connect(db_path)
c = conn.cursor()

folders = [
    '.tmp.drivedownload',
    'keywords_output'
]

print("Checking for folders in DB:")
for f in folders:
    c.execute("SELECT id, path FROM folders WHERE path LIKE ?", (f'%{f}%',))
    rows = c.fetchall()
    if rows:
        print(f"Found {len(rows)} entries for {f}:")
        for r in rows[:5]:
            print(f"  {r}")
    else:
        print(f"No entries for {f}")

print("\nChecking for images in these folders:")
for f in folders:
    c.execute("SELECT count(*) FROM images WHERE file_path LIKE ?", (f'%{f}%',))
    count = c.fetchone()[0]
    print(f"  {f}: {count} images")

conn.close()
