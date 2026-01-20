
import sqlite3
import os

db_path = 'scoring_history.db'
if not os.path.exists(db_path):
    print("DB not found")
    exit()

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Patterns to remove
exact_matches = ['.']

print("Removing unwanted folders from DB...")
total_deleted = 0
for p in exact_matches:
    c.execute("DELETE FROM folders WHERE path = ?", (p,))
    count = c.rowcount
    if count > 0:
        print(f"Deleted {count} records matching '{p}'")
        total_deleted += count

conn.commit()
conn.close()
print(f"Cleanup complete. Total records deleted: {total_deleted}")
