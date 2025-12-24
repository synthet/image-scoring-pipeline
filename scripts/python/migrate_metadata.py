import sqlite3
import json
import os
import sys

# Add project root to path to import modules if needed, but we'll stick to raw sqlite here for simplicity
# actually we need to know the DB path. It's relative to execution or absolute.
# We will assume it's run from project root.

DB_FILE = "scoring_history.db"

def migrate():
    if not os.path.exists(DB_FILE):
        print(f"Database file not found at {os.path.abspath(DB_FILE)}")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # check columns exist
    c.execute("PRAGMA table_info(images)")
    columns = [row[1] for row in c.fetchall()]
    if "rating" not in columns:
        print("Adding column `rating`...")
        c.execute("ALTER TABLE images ADD COLUMN rating INTEGER")
    
    if "label" not in columns:
        print("Adding column `label`...")
        c.execute("ALTER TABLE images ADD COLUMN label TEXT")

    print("Fetching images...")
    c.execute("SELECT id, scores_json, rating, label FROM images")
    rows = c.fetchall()
    
    updated_count = 0
    
    for row in rows:
        row_id = row['id']
        scores_json = row['scores_json']
        
        # Skip if already migrated (optional, but good for speed if re-run)
        # But maybe we want to force re-parse? Let's force re-parse to be safe.
        
        if not scores_json:
            continue
            
        try:
            data = json.loads(scores_json)
        except:
            print(f"Failed to parse JSON for image ID {row_id}")
            continue
            
        # Extraction Logic (Mirrors db.py/webui.py)
        nef_meta = None
        if "nef_metadata" in data: # Direct
             nef_meta = data["nef_metadata"]
        elif "full_results" in data and "summary" in data["full_results"]:
             nef_meta = data["full_results"]["summary"].get("nef_metadata")
        elif "summary" in data: # Legacy
             nef_meta = data["summary"].get("nef_metadata")
        
        rating = 0
        label = ""
        
        if nef_meta:
            rating = nef_meta.get("rating", 0)
            label = nef_meta.get("label", "")
            
        # Update
        c.execute("UPDATE images SET rating = ?, label = ? WHERE id = ?", (rating, label, row_id))
        updated_count += 1
        
    conn.commit()
    conn.close()
    print(f"Migration completed. Updated {updated_count} rows.")

if __name__ == "__main__":
    migrate()
