
import sqlite3
import os

db_path = 'scoring_history.db'
if not os.path.exists(db_path):
    print("DB not found")
    exit()

conn = sqlite3.connect(db_path)
c = conn.cursor()

print("Checking for '.' folder in DB:")
# Check for exact match or variations
patterns = ['.', './', '/.', '\\.']
for p in patterns:
    c.execute("SELECT id, path FROM folders WHERE path = ?", (p,))
    rows = c.fetchall()
    if rows:
        print(f"Found match for '{p}':")
        for r in rows:
            print(f"  {r}")

# Also check for empty path
c.execute("SELECT id, path FROM folders WHERE path = '' OR path IS NULL")
rows = c.fetchall()
if rows:
    print(f"Found empty/null paths:")
    for r in rows:
        print(f"  {r}")

conn.close()
