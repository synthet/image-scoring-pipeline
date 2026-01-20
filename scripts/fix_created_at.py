import os
import sys
import datetime
from pathlib import Path

# Setup path to import modules
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from modules import db, utils

def fix_created_at():
    print("Starting database timestamp migration...")
    conn = db.get_db()
    c = conn.cursor()
    
    # Get all images
    c.execute("SELECT id, file_path, created_at FROM images")
    rows = c.fetchall()
    
    print(f"Found {len(rows)} images to process.")
    
    updates = []
    
    for i, row in enumerate(rows):
        img_id = row['id']
        file_path = row['file_path']
        current_created_at = row['created_at']
        
        # Get actual creation time
        actual_time = utils.get_image_creation_time(file_path)
        
        if not actual_time:
            # print(f"Skipping {file_path}: File not found or no date")
            continue
            
        updates.append((actual_time, img_id))
        
        if len(updates) >= 1000:
            print(f"Applying batch of {len(updates)} updates... (Progress: {i + 1} / {len(rows)})")
            c.executemany("UPDATE images SET created_at = ? WHERE id = ?", updates)
            conn.commit()
            updates = []
            print(f"Batch committed.", end="\r")

    if updates:
        print(f"\nApplying final {len(updates)} updates...")
        c.executemany("UPDATE images SET created_at = ? WHERE id = ?", updates)
        conn.commit()
    
    conn.close()
    print("\nMigration complete.")

if __name__ == "__main__":
    fix_created_at()
