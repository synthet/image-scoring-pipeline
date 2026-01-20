import sqlite3
import os

DB_FILE = "scoring_history.db"
TARGET_FILE = r"D:/Photos/Z8/180-600mm/2025/2025-11-01/DSC_3953.NEF"

# Normalize path to match DB
TARGET_FILE = os.path.normpath(TARGET_FILE).replace('\\', '/')
# DB might store as /mnt/d/... or D:/... depending on history. 
# But let's try strict match or partial.

def check():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Try finding exact or partial
    c.execute("SELECT id, file_path, created_at FROM images WHERE file_path LIKE ?", (f"%DSC_3953.NEF",))
    rows = c.fetchall()
    
    for row in rows:
        print(f"ID: {row[0]}")
        print(f"Path: {row[1]}")
        print(f"Created At: {row[2]}")
        
    conn.close()

if __name__ == "__main__":
    check()
