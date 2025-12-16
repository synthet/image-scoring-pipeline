
import sys
import os
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules import db, utils

def backfill_hashes(force=False):
    """
    Iterates over all images in the DB.
    If 'image_hash' is missing (or force=True), computes it and updates the DB.
    """
    # Ensure DB has latest schema
    db.init_db()
    
    print("Starting hash backfill...")
    conn = db.get_db()
    c = conn.cursor()
    
    # Get all potential candidates
    if force:
        query = "SELECT id, file_path FROM images"
    else:
        query = "SELECT id, file_path FROM images WHERE image_hash IS NULL OR image_hash = ''"
        
    c.execute(query)
    rows = c.fetchall()
    
    total = len(rows)
    print(f"Found {total} images to process.")
    
    updated_count = 0
    error_count = 0
    
    for i, row in enumerate(rows):
        img_id = row['id'] if 'id' in row.keys() else row[0]
        file_path = row['file_path'] if 'file_path' in row.keys() else row[1]
        
        # Calculate Hash
        img_hash = utils.compute_file_hash(file_path)
        
        if img_hash:
            # Update DB
            try:
                c.execute("UPDATE images SET image_hash = ? WHERE id = ?", (img_hash, img_id))
                
                # Also start populating file_paths table (Migration)
                # We can't call db.register_image_path here because we have an open cursor/transaction
                # So we execute direct SQL or commit and call it.
                # Since we are inside a loop with a transaction, let's just insert here.
                c.execute("INSERT OR REPLACE INTO file_paths (image_id, path, last_seen) VALUES (?, ?, ?)", 
                          (img_id, file_path, datetime.now()))
                
                updated_count += 1
                if updated_count % 10 == 0:
                     print(f"Progress: {i+1}/{total} - Updated {updated_count}")
                     conn.commit() # Commit periodically
            except Exception as e:
                print(f"Error updating DB for {file_path}: {e}")
                error_count += 1
        else:
            print(f"Skipping {file_path} - File not found or error.")
            error_count += 1
            
    conn.commit()
    conn.close()
    print(f"Backfill complete.")
    print(f"Updated: {updated_count}")
    print(f"Errors: {error_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill image hashes in DB")
    parser.add_argument("--force", action="store_true", help="Re-calculate all hashes even if present")
    args = parser.parse_args()
    
    backfill_hashes(args.force)
