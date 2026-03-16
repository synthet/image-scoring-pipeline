import sys
import os

# Add image-scoring to path to use its db module
sys.path.append(r"d:\Projects\image-scoring")
from modules import db

def check_paths():
    try:
        conn = db.get_db()
        cur = conn.cursor()
        
        # Check for the specific problematic paths
        paths = [
            '/mnt/d/Photos/Z6ii/28-400mm/2026/2026-03-15/DSC_9545.NEF',
            '/mnt/d/Photos/Z6ii/28-400mm/2026/2026-03-15/DSC_9548.NEF'
        ]
        
        for path in paths:
            print(f"Checking path: {path}")
            cur.execute("SELECT id, file_path, folder_id FROM images WHERE file_path = ?", (path,))
            rows = cur.fetchall()
            if rows:
                for row in rows:
                    print(f"  FOUND: ID={row[0]}, PATH='{row[1]}', FOLDER_ID={row[2]}")
            else:
                print("  NOT FOUND (exact match)")
                
            # Try LIKE match to see if there are similar paths with different casing or separators
            basename = os.path.basename(path)
            cur.execute("SELECT id, file_path, folder_id FROM images WHERE file_path LIKE ?", (f"%{basename}%",))
            rows = cur.fetchall()
            if rows:
                print(f"  LIKE matches for '{basename}':")
                for row in rows:
                    print(f"    ID={row[0]}, PATH='{row[1]}', FOLDER_ID={row[2]}")
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_paths()
