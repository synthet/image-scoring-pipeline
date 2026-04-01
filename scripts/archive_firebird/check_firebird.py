from modules import db
import os

print("Connecting to Firebird...")
conn = db.get_db()
c = conn.cursor()

try:
    c.execute("SELECT COUNT(*) FROM images")
    count = c.fetchone()[0]
    print(f"Total Images: {count}")

    c.execute("SELECT COUNT(*) FROM folders")
    f_count = c.fetchone()[0]
    print(f"Total Folders: {f_count}")

    # Check a timestamp
    c.execute("SELECT first 1 created_at FROM images ORDER BY created_at DESC")
    row = c.fetchone()
    if row:
        print(f"Latest Image Date: {row[0]} (Type: {type(row[0])})")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    conn.close()
