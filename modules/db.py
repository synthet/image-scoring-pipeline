import sqlite3
import json
import os
import datetime
import logging
from pathlib import Path

DB_FILE = "scoring_history.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def get_image_count(rating_filter=None, label_filter=None, keyword_filter=None, min_score_general=0, min_score_aesthetic=0, min_score_technical=0, date_range=None, folder_path=None):
    conn = get_db()
    c = conn.cursor()
    
    query = "SELECT COUNT(*) FROM images"
    params = []
    conditions = []
    
    if rating_filter:
        placeholders = ','.join(['?'] * len(rating_filter))
        # Handle "Unrated" (0) separate or included? 
        # UI sends ["1", "2"] etc. "Unrated" might be sent as "0" or "Unrated"
        # Let's assume input is list of ints. "Unrated" maps to 0.
        conditions.append(f"rating IN ({placeholders})")
        params.extend(rating_filter)
        
    if label_filter:
        # Handle "None" label
        clean_labels = [l for l in label_filter if l != "None"]
        has_none = "None" in label_filter
        
        lbl_conds = []
        if clean_labels:
            placeholders = ','.join(['?'] * len(clean_labels))
            lbl_conds.append(f"label IN ({placeholders})")
            params.extend(clean_labels)
            
        if has_none:
            lbl_conds.append("(label IS NULL OR label = '')")
            
        if lbl_conds:
            conditions.append(f"({' OR '.join(lbl_conds)})")
            
    if keyword_filter and keyword_filter.strip():
        conditions.append("keywords LIKE ?")
        params.append(f"%{keyword_filter.strip()}%")

    # Score Filters
    if min_score_general > 0:
        conditions.append("score_general >= ?")
        params.append(min_score_general)
    
    if min_score_aesthetic > 0:
        conditions.append("score_aesthetic >= ?")
        params.append(min_score_aesthetic)

    if min_score_technical > 0:
        conditions.append("score_technical >= ?")
        params.append(min_score_technical)
        
    # Date Filter
    if date_range:
        start_date, end_date = date_range
        print(f"DEBUG: Date Range: {start_date} to {end_date}")
        if start_date:
            conditions.append("date(created_at) >= date(?)")
            params.append(start_date)
        if end_date:
            conditions.append("date(created_at) <= date(?)")
            params.append(end_date)
            
    if folder_path:
        folder_id = get_or_create_folder(folder_path)
        conditions.append("folder_id = ?")
        params.append(folder_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    c.execute(query, tuple(params))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_images_paginated(page=1, page_size=50, sort_by="score", order="desc", rating_filter=None, label_filter=None, keyword_filter=None, min_score_general=0, min_score_aesthetic=0, min_score_technical=0, date_range=None, folder_path=None):
    conn = get_db()
    c = conn.cursor()
    offset = (page - 1) * page_size
    
    query = "SELECT * FROM images"
    params = []
    conditions = []
    
    if rating_filter:
        placeholders = ','.join(['?'] * len(rating_filter))
        conditions.append(f"rating IN ({placeholders})")
        params.extend(rating_filter)
        
    if label_filter:
        clean_labels = [l for l in label_filter if l != "None"]
        has_none = "None" in label_filter
        
        lbl_conds = []
        if clean_labels:
            placeholders = ','.join(['?'] * len(clean_labels))
            lbl_conds.append(f"label IN ({placeholders})")
            params.extend(clean_labels)
            
        if has_none:
            lbl_conds.append("(label IS NULL OR label = '')")
            
        if lbl_conds:
            conditions.append(f"({' OR '.join(lbl_conds)})")
            
    if keyword_filter and keyword_filter.strip():
        conditions.append("keywords LIKE ?")
        params.append(f"%{keyword_filter.strip()}%")
        
    # Score Filters
    if min_score_general > 0:
        conditions.append("score_general >= ?")
        params.append(min_score_general)
    
    if min_score_aesthetic > 0:
        conditions.append("score_aesthetic >= ?")
        params.append(min_score_aesthetic)

    if min_score_technical > 0:
        conditions.append("score_technical >= ?")
        params.append(min_score_technical)

    # Date Filter
    if date_range:
        start_date, end_date = date_range
        if start_date:
            conditions.append("date(created_at) >= date(?)")
            params.append(start_date)
        if end_date:
            conditions.append("date(created_at) <= date(?)")
            params.append(end_date)
            
    
    if folder_path:
        folder_id = get_or_create_folder(folder_path)
        conditions.append("folder_id = ?")
        params.append(folder_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += f" ORDER BY {sort_by} {order.upper()} LIMIT ? OFFSET ?"
    params.extend([page_size, offset])
    
    c.execute(query, tuple(params))
    rows = c.fetchall()
    conn.close()
    return rows

def get_filtered_paths(rating_filter=None, label_filter=None, keyword_filter=None, min_score_general=0, min_score_aesthetic=0, min_score_technical=0, date_range=None, folder_path=None):
    """
    Returns a list of file_paths matching the filters (No pagination).
    """
    conn = get_db()
    c = conn.cursor()
    
    query = "SELECT file_path FROM images"
    params = []
    conditions = []
    
    if rating_filter:
        placeholders = ','.join(['?'] * len(rating_filter))
        conditions.append(f"rating IN ({placeholders})")
        params.extend(rating_filter)
        
    if label_filter:
        clean_labels = [l for l in label_filter if l != "None"]
        has_none = "None" in label_filter
        
        lbl_conds = []
        if clean_labels:
            placeholders = ','.join(['?'] * len(clean_labels))
            lbl_conds.append(f"label IN ({placeholders})")
            params.extend(clean_labels)
            
        if has_none:
            lbl_conds.append("(label IS NULL OR label = '')")
            
        if lbl_conds:
            conditions.append(f"({' OR '.join(lbl_conds)})")
            
    if keyword_filter and keyword_filter.strip():
        conditions.append("keywords LIKE ?")
        params.append(f"%{keyword_filter.strip()}%")
        
    # Score Filters
    if min_score_general > 0:
        conditions.append("score_general >= ?")
        params.append(min_score_general)
    
    if min_score_aesthetic > 0:
        conditions.append("score_aesthetic >= ?")
        params.append(min_score_aesthetic)

    if min_score_technical > 0:
        conditions.append("score_technical >= ?")
        params.append(min_score_technical)

    # Date Filter
    if date_range:
        start_date, end_date = date_range
        print(f"DEBUG: Date Range: {start_date} to {end_date}")
        if start_date:
            conditions.append("date(created_at) >= date(?)")
            params.append(start_date)
        if end_date:
            conditions.append("date(created_at) <= date(?)")
            params.append(end_date)
            
    if folder_path:
        folder_id = get_or_create_folder(folder_path)
        conditions.append("folder_id = ?")
        params.append(folder_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    c.execute(query, tuple(params))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def image_exists(file_path, current_version=None):
    conn = get_db()
    c = conn.cursor()
    # Check existence AND if score is valid (not 0 or NULL)
    c.execute("SELECT score, model_version, score_general, thumbnail_path FROM images WHERE file_path = ?", (file_path,))
    row = c.fetchone()
    conn.close()
    
    if row:
        score = row['score'] if 'score' in row.keys() else row[0] # Handle Row or tuple
        
        # Check if score is valid
        if score is None or score <= 0:
            return False 

        # Check thumbnail existence (User Requirement)
        thumb = row['thumbnail_path'] if 'thumbnail_path' in row.keys() else row[3]
        if not thumb:
             return False

        # Check version if provided
        if current_version:
             db_version = row['model_version'] if 'model_version' in row.keys() else row[1]
             if db_version != current_version:
                 return False # Version mismatch, treat as stale
            
             # Also strict check for score_general if we are strictly version checking
             sg = row['score_general'] if 'score_general' in row.keys() else row[2]
             if sg is None or sg <= 0:
                 return False

        return True
    return False

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Jobs table
    c.execute('''CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        input_path TEXT,
        status TEXT, -- pending, running, completed, failed
        created_at TIMESTAMP,
        completed_at TIMESTAMP,
        log TEXT
    )''')
    
    # Images table
    c.execute('''CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        file_path TEXT UNIQUE,
        file_name TEXT,
        file_type TEXT,
        score REAL,
        keywords TEXT,
        title TEXT,
        description TEXT,
        metadata TEXT,
        thumbnail_path TEXT,
        scores_json TEXT, -- Full JSON output from scorer
        created_at TIMESTAMP,
        FOREIGN KEY(job_id) REFERENCES jobs(id)
    )''')
    
    
    # Check for missing columns (Schema Migration)
    c.execute("PRAGMA table_info(images)")
    columns = [row[1] for row in c.fetchall()]
    
    if "file_type" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN file_type TEXT")
    
    if "thumbnail_path" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN thumbnail_path TEXT")
        
    if "scores_json" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN scores_json TEXT")


    # Migration for Stacks
    if "stack_id" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN stack_id INTEGER")
        c.execute("CREATE INDEX IF NOT EXISTS idx_stack_id ON images(stack_id)")
    
    # Composite index for efficient cover image lookup in stacks (stack_id + score for ordering)
    c.execute("CREATE INDEX IF NOT EXISTS idx_stack_score_general ON images(stack_id, score_general DESC) WHERE stack_id IS NOT NULL")

    # Migration for Folders
    if "folder_id" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN folder_id INTEGER")
        c.execute("CREATE INDEX IF NOT EXISTS idx_folder_id ON images(folder_id)")

    # Stacks table
    c.execute('''CREATE TABLE IF NOT EXISTS stacks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        best_image_id INTEGER,
        created_at TIMESTAMP,
        FOREIGN KEY(best_image_id) REFERENCES images(id)
    )''')
    
    # Folders table
    c.execute('''CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE,
        parent_id INTEGER,
        created_at TIMESTAMP
    )''')

    # Cluster Progress table

    c.execute('''CREATE TABLE IF NOT EXISTS cluster_progress (
        folder_path TEXT PRIMARY KEY,
        last_run TIMESTAMP
    )''')



    # Migration for individual scores
    if "score_spaq" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN score_spaq REAL")
    if "score_ava" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN score_ava REAL")
    if "score_koniq" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN score_koniq REAL")
    if "score_paq2piq" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN score_paq2piq REAL")
    if "score_liqe" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN score_liqe REAL")

    # Migration for Weighted Scores and Version
    if "model_version" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN model_version TEXT")
    if "score_technical" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN score_technical REAL")
    if "score_aesthetic" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN score_aesthetic REAL")
    if "score_general" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN score_general REAL")

    # Migration for Filtering
    if "rating" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN rating INTEGER")
    if "label" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN label TEXT")

    # Migration for Deduplication
    if "image_hash" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN image_hash TEXT")
        c.execute("CREATE INDEX IF NOT EXISTS idx_image_hash ON images(image_hash)")

    # Migration for Multi-Path (File Paths Table)
    c.execute('''CREATE TABLE IF NOT EXISTS file_paths (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_id INTEGER,
        path TEXT,
        last_seen TIMESTAMP,
        FOREIGN KEY(image_id) REFERENCES images(id),
        UNIQUE(image_id, path)
    )''')
    
    conn.commit()
    conn.close()

    # Separate connection for migrations to handle errors gracefully
    conn = get_db()
    c = conn.cursor()
    
    try:
        c.execute("ALTER TABLE images ADD COLUMN title TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE images ADD COLUMN description TEXT")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()

def get_image_by_hash(image_hash):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM images WHERE image_hash = ?", (image_hash,))
    row = c.fetchone()
    conn.close()
    if row:
        data = dict(row)
        data['file_paths'] = get_all_paths(data['id'])
        return data
    return None

def update_image_path(image_hash, new_path):
    conn = get_db()
    c = conn.cursor()
    try:
        # Also need to update file_name
        from pathlib import Path
        new_name = Path(new_path).name
        c.execute("UPDATE images SET file_path = ?, file_name = ? WHERE image_hash = ?", (new_path, new_name, image_hash))
        
        # Also register in file_paths
        # We need image_id
        c.execute("SELECT id FROM images WHERE image_hash = ?", (image_hash,))
        row = c.fetchone()
        if row:
            img_id = row[0]
            c.execute("INSERT OR REPLACE INTO file_paths (image_id, path, last_seen) VALUES (?, ?, ?)", 
                      (img_id, new_path, datetime.datetime.now()))
        

        conn.commit()
        # Post-update folder fix
        try:
             update_image_folder_id(image_hash=image_hash) 
        except: pass
        
        return True
    except Exception as e:
        logging.error(f"Failed to update path for hash {image_hash}: {e}")
        return False
    finally:
        conn.close()

def update_image_folder_id(image_hash=None, image_id=None):
    """
    Helper to update folder_id for a single image.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        if image_hash:
             c.execute("SELECT id, file_path FROM images WHERE image_hash = ?", (image_hash,))
        elif image_id:
             c.execute("SELECT id, file_path FROM images WHERE id = ?", (image_id,))
        else:
             return

        row = c.fetchone()
        if row:
             img_id = row[0]
             path = row[1]
             if path:
                 dirname = os.path.dirname(path)
                 dirname = os.path.normpath(dirname)
                 # This calls get_or_create_folder which opens its own connection. 
                 # Should be fine if we are not holding a write lock on main conn.
                 conn.close() # Close read lock
                 
                 fid = get_or_create_folder(dirname)
                 
                 conn = get_db()
                 c = conn.cursor()
                 c.execute("UPDATE images SET folder_id = ? WHERE id = ?", (fid, img_id))
                 conn.commit()
    except Exception as e:
        print(f"Error updating folder_id: {e}")
    finally:
        # conn close handled
        try: conn.close()
        except: pass

def register_image_path(image_id, path):

    """
    Registers a path for a given image ID.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT OR REPLACE INTO file_paths (image_id, path, last_seen) VALUES (?, ?, ?)", 
                  (image_id, path, datetime.datetime.now()))
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to register path {path} for image {image_id}: {e}")
    finally:
        conn.close()



def get_all_paths(image_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT path FROM file_paths WHERE image_id = ?", (image_id,))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_folder_by_id(folder_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT path FROM folders WHERE id = ?", (folder_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def get_or_create_folder(folder_path):
    """
    Gets folder ID from cache/DB, creating it if it doesn't exist.
    Recursively creates parent folders to establish hierarchy.
    """
    # Normalize path
    folder_path = os.path.normpath(folder_path)
    
    # Base case for recursion / root check
    # On Windows, os.path.dirname("D:\\") is "D:\\". 
    # Stop if parent is same as current or empty.
    parent_path = os.path.dirname(folder_path)
    if not parent_path or parent_path == folder_path:
        # It's a root or top level?
        # Just create/get it with no parent.
        parent_id = None
    else:
        # Recursive call to get/create parent first
        # We assume this won't be too deep (max 10-20 levels typically)
        parent_id = get_or_create_folder(parent_path)

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id, parent_id FROM folders WHERE path = ?", (folder_path,))
        row = c.fetchone()
        if row:
            # Check if parent_id needs update (if it was created without parent before)
            # Only update if we have a valid parent_id and it's missing in DB
            curr_pid = row[1]
            if parent_id and curr_pid != parent_id:
                # Update parent linkage
                c.execute("UPDATE folders SET parent_id = ? WHERE id = ?", (parent_id, row[0]))
                conn.commit()
            return row[0]
        
        c.execute("INSERT INTO folders (path, parent_id, created_at) VALUES (?, ?, ?)", 
                  (folder_path, parent_id, datetime.datetime.now()))
        conn.commit()
        return c.lastrowid
    except Exception as e:
        # Race condition or error?
        # Retry select
        try:
             c.execute("SELECT id FROM folders WHERE path = ?", (folder_path,))
             row = c.fetchone()
             if row: return row[0]
        except: pass
        
        logging.error(f"Error getting/creating folder {folder_path}: {e}")
        return None
    finally:
        conn.close()

def rebuild_folder_cache():
    """
    Scans all images, populates folders table with full hierarchy, and updates images.folder_id.
    """
    print("Rebuilding folder cache with hierarchy...")
    conn = get_db()
    c = conn.cursor()
    
    # 1. Get all unique folder paths from images
    c.execute("SELECT DISTINCT file_path FROM images")
    rows = c.fetchall()
    conn.close() # Close mainly to avoid long read block if we write later (though we re-open in loop: inefficient but safe)
    
    unique_dirs = set()
    for row in rows:
        if row[0]:
            unique_dirs.add(os.path.dirname(row[0]))
            
    sorted_dirs = sorted(list(unique_dirs))
    
    # 2. Iterate and create folders (recursive logic in get_or_create_folder handles hierarchy)
    # We use a separate cache map to avoid slamming DB for get_or_create if we ran this often,
    # but get_or_create_folder handles logic.
    # To optimize: maybe just call get_or_create_folder for each unique dir.
    
    print(f"Found {len(sorted_dirs)} unique image directories. Processing hierarchy...")
    
    folder_map = {} # path -> id
    
    for d in sorted_dirs:
        # This will create d and all its parents
        fid = get_or_create_folder(d)
        if fid:
            folder_map[d] = fid
            
    # 3. Update images folder_id
    print("Updating image folder_ids...")
    conn = get_db()
    c = conn.cursor()
    
    # Batch update? 
    # doing one by one is slow for 100k images.
    # Logic: update by folder path.
    # "UPDATE images SET folder_id = ? WHERE file_path LIKE ?" (too risky with partial matches?)
    # "UPDATE images SET folder_id = ? WHERE substr(file_path, 1, len(dir)) = dir ?" No.
    # Best: Iterate unique dirs, and update all images in that dir.
    # Since we know the dir path, we can do:
    # UPDATE images SET folder_id = <fid> WHERE file_path LIKE <dir> || '%';
    # AND verify dirname matches?
    # Or just iterate images?
    # Iterate images might be 100k updates.
    # Iterate folders is 1k updates.
    # Let's try folder based update.
    
    count = 0
    for d, fid in folder_map.items():
        # Ensure path ends with separator for like query to contain it
        # BUT wait, file_path includes filename.
        # "D:\Photos\Img.jpg" dirname is "D:\Photos"
        # We want UPDATE images SET folder_id=? WHERE file_path logic.
        # We can't express "dirname(file_path) == d" easily in SQL.
        # BUT we can iterate images with NO folder_id or ALL images?
        pass

    # Fallback: Loop images again?
    # Or rely on python.
    # Let's simple-loop images. 
    # To speed up: SELECT id, file_path, folder_id FROM images WHERE folder_id IS NULL OR folder_id = 0?
    # Or force update all.
    
    c.execute("SELECT id, file_path FROM images")
    img_rows = c.fetchall()
    
    batch = []
    
    for row in img_rows:
        img_id = row[0]
        path = row[1]
        if not path: continue
        
        d = os.path.dirname(path)
        # Normalize
        d = os.path.normpath(d)
        
        fid = folder_map.get(d)
        if fid:
            batch.append((fid, img_id))
            
        if len(batch) >= 1000:
            c.executemany("UPDATE images SET folder_id = ? WHERE id = ?", batch)
            count += len(batch)
            batch = []
            
    if batch:
        c.executemany("UPDATE images SET folder_id = ? WHERE id = ?", batch)
        count += len(batch)
            
    conn.commit()
    conn.close()
    
    msg = f"Folder cache rebuild complete. Processed {len(sorted_dirs)} folders, updated {count} images."
    print(msg)
    return msg



def get_all_folders():
    """
    Returns a sorted list of all unique folder paths from the folders table.
    Does NOT auto-rebuild to avoid blocking the UI - use rebuild_folder_cache() explicitly.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT path FROM folders ORDER BY path")
    rows = c.fetchall()
    conn.close()
    
    return [row['path'] for row in rows]

def get_images_by_folder(folder_path):
    """
    Returns all images located immediately in the specified folder using folder_id.
    """
    # Normalize
    folder_path = os.path.normpath(folder_path)
    
    # Get ID
    folder_id = get_or_create_folder(folder_path) # retrieving id mainly
    
    if not folder_id:
        return []

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM images WHERE folder_id = ? ORDER BY file_name", (folder_id,))
    rows = c.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def create_job(input_path):


    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO jobs (input_path, status, created_at) VALUES (?, ?, ?)",
              (input_path, "pending", datetime.datetime.now()))
    job_id = c.lastrowid
    conn.commit()
    conn.close()
    return job_id

    return job_id

def update_job_status(job_id, status, log=None):
    conn = get_db()
    c = conn.cursor()
    if status in ["completed", "failed"]:
        c.execute("UPDATE jobs SET status = ?, completed_at = ?, log = ? WHERE id = ?",
                  (status, datetime.datetime.now(), log, job_id))
    else:
        c.execute("UPDATE jobs SET status = ?, log = ? WHERE id = ?",
                  (status, log, job_id))
    conn.commit()
    conn.close()

def get_jobs(limit=50):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_images(sort_by="score", order="desc", limit=100):
    conn = get_db()
    c = conn.cursor()
    query = f"SELECT * FROM images ORDER BY {sort_by} {order.upper()} LIMIT ?"
    c.execute(query, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def sync_folder_to_db(folder_path, job_id=None):
    """
    Scans a folder for .json files (generated by scoring) and upserts them to DB.
    """
    conn = get_db()
    c = conn.cursor()
    
    count = 0
    # Find all JSONs that look like scoring results
    # We assume valid scoring results have 'summary' key
    folder = Path(folder_path)
    if not folder.exists():
        return 0

    for json_file in folder.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Simple validation: checks for 'summary' or 'average_normalized_score'
            if "summary" not in data and "average_normalized_score" not in data:
                continue

            # Handle different versions of JSON structure if needed
            # Assuming current structure based on batch_process_images.py
            
            # Extract score (General)
            score = 0
            if "summary" in data and "weighted_scores" in data["summary"]:
                score = data["summary"]["weighted_scores"].get("general", 0)
            elif "summary" in data:
                 # Legacy fallback
                 score = data["summary"].get("average_normalized_score", 0)
                
            # Find original image path
            # The JSON usually contains "image_path" but it might be a WSL path if generated inside WSL?
            # Actually batch_process_images.py runs inside WSL but might save WSL paths.
            # We need to map it back or just trust the JSON filename matching the image?
            # Let's rely on the JSON's stated path if it exists, or infer from filename.
            
            image_path = data.get("image_path", "")
            if not image_path:
                # Infer from JSON name
                # image.jpg -> image.json
                stem = json_file.stem
                # Try to find the image file
                for ext in ['.jpg', '.nef', '.png']:
                    probe = folder / (stem + ext)
                    if probe.exists():
                        image_path = str(probe)
                        break
            
            if not image_path:
                image_path = str(json_file.with_suffix('')) # Fallback
                
            file_name = Path(image_path).name
            
            # Upsert
            c.execute('''INSERT OR REPLACE INTO images 
                         (job_id, file_path, file_name, score, scores_json, created_at)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (job_id, str(image_path), file_name, score, json.dumps(data), datetime.datetime.now()))
            
            count += 1
        except Exception as e:
            logging.error(f"Failed to sync {json_file}: {e}")
            
    conn.commit()
    conn.close()
    return count

def upsert_image(job_id, result):
    """
    Upsert a single image result from the streaming output.
    result is a generic dictionary (the JSON output from batch_process_images).
    """
    conn = get_db()
    c = conn.cursor()
    
    # DEBUG
    logging.debug(f"DEBUG UPSERT ID: {result.get('image_name')}")
    logging.debug(f"DEBUG UPSERT TECH: {result.get('score_technical')}")
    logging.debug(f"DEBUG UPSERT GEN: {result.get('score_general')}")

    # Extract fields
    image_path = result.get("image_path", "")
    file_name = result.get("image_name", Path(image_path).name)
    file_type = Path(image_path).suffix.lower().lstrip('.')
    
    # Handle score location variation (summary vs direct)
    # New Standard: "score" in root of engine result (which comes from weighted_scores['general'])
    # Or parsing directly from stored JSON if re-syncing
    
    score = 0
    normalized_score = 0
    
    if "score" in result:
        score = result["score"]
    elif "summary" in result and "weighted_scores" in result["summary"]:
         score = result["summary"]["weighted_scores"].get("general", 0)
    elif "summary" in result: # Legacy fallback
        score = result["summary"].get("average_normalized_score", 0)
    
    # normalized_score removal
    # normalized_score = score # General score is already 0-1
        
    # Individual Scores
    individual_scores = result.get("individual_scores", {})
    models_scores = result.get("models", {})
    
    def get_ind_score(name):
        # Try 'models' first (new format)
        if name in models_scores:
            m_data = models_scores[name]
            if isinstance(m_data, dict):
                 return m_data.get("normalized_score", m_data.get("score", 0))
            return 0
            
        # Try 'individual_scores' (legacy format)
        val = individual_scores.get(name)
        if isinstance(val, dict):
            return val.get("normalized_score", val.get("score", 0))
        if isinstance(val, (int, float)):
            return val
        return 0

    score_spaq = get_ind_score("spaq")
    score_ava = get_ind_score("ava")
    score_koniq = get_ind_score("koniq")
    score_paq2piq = get_ind_score("paq2piq")
    score_liqe = get_ind_score("liqe")
        
    # Weighted Scores
    # Try to get from result (if passed from engine) or parse from summary
    score_technical = 0
    score_aesthetic = 0
    score_general = 0
    
    if "score_technical" in result:
        score_technical = result["score_technical"]
        score_aesthetic = result["score_aesthetic"]
        score_general = result["score_general"]
    elif "summary" in result and "weighted_scores" in result["summary"]:
        ws = result["summary"]["weighted_scores"]
        score_technical = ws.get("technical", 0)
        score_aesthetic = ws.get("aesthetic", 0)
        score_general = ws.get("general", 0)
    elif "full_results" in result: 
        # Engine passes full_results
        ws = result["full_results"].get("summary", {}).get("weighted_scores", {})
        score_technical = ws.get("technical", 0)
        score_aesthetic = ws.get("aesthetic", 0)
        score_general = ws.get("general", 0)
        
    # Ensure main score matches general if not set
    if score == 0 and score_general > 0:
        score = score_general


    
    thumbnail_path = result.get("thumbnail_path")
    
    # Extract Version
    model_version = "0.0.0"
    if "version" in result:
        model_version = result["version"]
    elif "full_results" in result:
        model_version = result["full_results"].get("version", "0.0.0")

    # Extract Metadata (Rating, Label)
    rating = 0
    label = ""
    
    # Try finding in nef_metadata
    nef_meta = None
    if "nef_metadata" in result: # Direct
         nef_meta = result["nef_metadata"]
    elif "full_results" in result and "summary" in result["full_results"]:
         nef_meta = result["full_results"]["summary"].get("nef_metadata")
    elif "summary" in result: # Legacy
         nef_meta = result["summary"].get("nef_metadata")
         
    if nef_meta:
        rating = nef_meta.get("rating", 0)
        label = nef_meta.get("label", "")
    


    # Keywords & Metadata (if present)
    keywords = result.get("keywords", [])
    if isinstance(keywords, list):
        keywords = ",".join(keywords)
        
    title = result.get("title", "")
    description = result.get("description", "")
        
    metadata = result.get("metadata", {})
    if isinstance(metadata, dict):
        metadata = json.dumps(metadata)


    image_hash = result.get("image_hash", None)

    # Resolve Folder ID
    folder_id = None
    if image_path:
        try:
             folder_id = get_or_create_folder(os.path.dirname(image_path))
        except Exception as e:
             logging.error(f"Error resolving folder for {image_path}: {e}")

    c.execute('''INSERT OR REPLACE INTO images 
                 (job_id, file_path, file_name, file_type, 
                  score, 
                  score_spaq, score_ava, score_koniq, score_paq2piq, score_liqe,
                  score_technical, score_aesthetic, score_general, model_version,
                  rating, label,
                  keywords, title, description, metadata, scores_json, thumbnail_path, image_hash, folder_id, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (job_id, image_path, file_name, file_type, 
               score,
               score_spaq, score_ava, score_koniq, score_paq2piq, score_liqe,
               score_technical, score_aesthetic, score_general, model_version,
               rating, label,
               keywords, title, description, metadata, json.dumps(result), thumbnail_path, image_hash, folder_id, datetime.datetime.now()))
    
    # Get ID of inserted/updated record
    image_id = c.lastrowid
    # If it was a replace where ID didn't change, lastrowid might be 0 or unexpected depending on sqlite version/driver
    # But for INSERT OR REPLACE, it usually works. 
    # Safest is to query by hash or path if 0.
    if not image_id or image_id == 0:
        if image_hash:
             c.execute("SELECT id FROM images WHERE image_hash = ?", (image_hash,))
        else:
             c.execute("SELECT id FROM images WHERE file_path = ?", (image_path,))
        row = c.fetchone()
        if row:
            image_id = row[0]
            
    conn.commit()
    conn.close()
    
    # Register path in file_paths
    if image_id:
        register_image_path(image_id, image_path)



def get_image_details(file_path):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM images WHERE file_path = ?", (file_path,))
    row = c.fetchone()
    conn.close()
    if row:
        data = dict(row)
        data['file_paths'] = get_all_paths(data['id'])
        return data
    return {}


def delete_image(file_path):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM images WHERE file_path = ?", (file_path,))
    conn.commit()
    conn.close()

def backup_database(max_backups=5):
    """
    Creates a backup of the database file and rotates old backups.
    """
    if not os.path.exists(DB_FILE):
        return

    backup_dir = "backups"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"scoring_history_{timestamp}.db")

    try:
        # Copy file
        import shutil
        shutil.copy2(DB_FILE, backup_path)
        print(f"Database backup created: {backup_path}")

        # Rotate
        backups = sorted([os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith("scoring_history_") and f.endswith(".db")])
        
        while len(backups) > max_backups:
            oldest = backups.pop(0)
            try:
                os.remove(oldest)
                print(f"Removed old backup: {oldest}")
            except Exception as e:
                print(f"Failed to remove old backup {oldest}: {e}")

    except Exception as e:
        print(f"Backup failed: {e}")

def update_image_metadata(file_path, keywords, title, description, rating, label):
    """
    Updates the metadata fields for a given image path.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        # Also need to update scores_json if possible?
        # For now, just update the columns.
        
        c.execute('''UPDATE images 
                     SET keywords = ?, title = ?, description = ?, rating = ?, label = ?
                     WHERE file_path = ?''',
                  (keywords, title, description, rating, label, file_path))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Failed to update metadata for {file_path}: {e}")
        return False
    finally:
        conn.close()

def get_incomplete_records():
    """
    Retrieves records that have missing scores or metadata.
    Criteria:
    - Any model score <= 0 or NULL
    - Rating <= 0 or NULL
    - Label empty or NULL
    """
    conn = get_db()
    c = conn.cursor()
    
    # Check for missing individual scores
    score_checks = []
    models = ['spaq', 'ava', 'koniq', 'paq2piq', 'liqe']
    for m in models:
        score_checks.append(f"score_{m} IS NULL OR score_{m} <= 0")
        
    score_cond = " OR ".join(score_checks)
    
    query = f"""
        SELECT * FROM images 
        WHERE 
            (score <= 0 OR score IS NULL) OR
            (rating <= 0 OR rating IS NULL) OR
            (label IS NULL OR label = '') OR
            ({score_cond})
    """
    
    c.execute(query)
    rows = c.fetchall()
    conn.close()
    return rows

def export_db_to_json(output_path):
    """
    Exports the entire images table to a JSON file.
    """
    import json
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM images")
    rows = c.fetchall()
    conn.close()
    
    data = []
    for row in rows:
        item = dict(row)
        # Handle datetime serialization if necessary (e.g. created_at)
        # SQLite returns strings for timestamps usually, but just in case
        if 'created_at' in item and item['created_at']:
            item['created_at'] = str(item['created_at'])
            
        # Parse nested JSON strings for cleaner output?
        # scores_json is already a JSON string in DB. 
        # If we want the export to be a clean JSON object, we should probably parse it back to dict.
        # But for a raw backup, keeping it as string is safer. 
        # Let's try to parse it to make the export more usable.
        if 'scores_json' in item and isinstance(item['scores_json'], str):
            try:
                item['scores_json'] = json.loads(item['scores_json'])
            except:
                pass # Leave as string if fail
                
        if 'metadata' in item and isinstance(item['metadata'], str):
            try:
                item['metadata'] = json.loads(item['metadata'])
            except:
                pass
                
        data.append(item)
        
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True, f"Successfully exported {len(data)} records to {output_path}"
    except Exception as e:
        return False, f"Export failed: {e}"

# --- Stack Management ---

def clear_stacks():
    """
    Clears all stacks and resets stack_id in images.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM stacks")
        # Reset stack_id to NULL
        c.execute("UPDATE images SET stack_id = NULL")
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to clear stacks: {e}")
    finally:
        conn.close()

def create_stack(name, best_image_id=None):
    """
    Creates a new stack.
    """
    conn = get_db()
    c = conn.cursor()
    stack_id = None
    try:
        c.execute("INSERT INTO stacks (name, best_image_id, created_at) VALUES (?, ?, ?)",
                  (name, best_image_id, datetime.datetime.now()))
        stack_id = c.lastrowid
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to create stack: {e}")
    finally:
        conn.close()
    return stack_id

def update_image_stack_batch(updates):
    """
    Batch updates image stack_ids.
    updates: list of (stack_id, image_id) tuples
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.executemany("UPDATE images SET stack_id = ? WHERE id = ?", updates)
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to batch update image stacks: {e}")
    finally:
        conn.close()

def get_stacks():
    """
    Returns all stacks joined with their best image info.
    """
    conn = get_db()
    c = conn.cursor()
    # Join with images to get path of best image
    query = '''
        SELECT s.*, i.file_path as best_image_path, i.score_general as best_image_score,
        (SELECT COUNT(*) FROM images WHERE stack_id = s.id) as image_count
        FROM stacks s
        LEFT JOIN images i ON s.best_image_id = i.id
        ORDER BY s.id ASC
    '''
    c.execute(query)
    rows = c.fetchall()
    conn.close()
    return rows

def get_stacks_for_display(folder_path=None, sort_by="score_general", order="desc"):
    """
    Returns stacks with dynamic cover image based on sort criteria.
    Uses CTE with ROW_NUMBER() instead of correlated subquery for better performance.
    """
    conn = get_db()
    c = conn.cursor()
    
    # Resolve folder_id if path provided
    folder_id = None
    if folder_path:
        folder_id = get_or_create_folder(folder_path)
        if not folder_id:
            conn.close()
            return []

    # Map sort_by to column
    # If sort_by is invalid, default to score_general
    valid_cols = ["created_at", "id", "score_general", "score_technical", "score_aesthetic", 
                  "score_spaq", "score_ava", "score_koniq", "score_paq2piq", "score_liqe"]
    if sort_by not in valid_cols:
        sort_by = "score_general"
        
    agg_func = "MAX" if order.lower() == "desc" else "MIN"
    order_dir = order.upper()
    
    # Use CTE with ROW_NUMBER() to compute cover images in a single pass
    # This avoids the N+1 correlated subquery problem
    
    where_clause = ""
    params = []
    if folder_id:
        where_clause = "WHERE i.folder_id = ?"
        params.append(folder_id)
        
    query = f'''
        WITH ranked_covers AS (
            SELECT 
                stack_id,
                COALESCE(NULLIF(thumbnail_path, ''), file_path) as cover_path,
                ROW_NUMBER() OVER (PARTITION BY stack_id ORDER BY {sort_by} {order_dir}) as rn
            FROM images
            WHERE stack_id IS NOT NULL
        )
        SELECT 
            s.id, 
            s.name, 
            COUNT(i.id) as image_count,
            {agg_func}(i.{sort_by}) as sort_val,
            rc.cover_path
        FROM stacks s
        JOIN images i ON s.id = i.stack_id
        LEFT JOIN ranked_covers rc ON s.id = rc.stack_id AND rc.rn = 1
        {where_clause}
        GROUP BY s.id
        ORDER BY sort_val {order_dir}
    '''
    
    c.execute(query, tuple(params))
    rows = c.fetchall()
    conn.close()
    return rows

def get_images_in_stack(stack_id):
    """
    Returns all images in a stack.
    """
    conn = get_db()
    c = conn.cursor()
    query = "SELECT * FROM images WHERE stack_id = ? ORDER BY score_general DESC"
    c.execute(query, (stack_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_stack_count():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM stacks")
    count = c.fetchone()[0]
    conn.close()
    return count

def get_clustered_folders():
    """
    Returns a set of folders that have been clustered.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT folder_path FROM cluster_progress")
        rows = c.fetchall()
        return {row[0] for row in rows}
    except Exception as e:
        logging.error(f"Error reading cluster progress: {e}")
        return set()
    finally:
        conn.close()

def mark_folder_clustered(folder_path):
    """
    Marks a folder as successfully clustered.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT OR REPLACE INTO cluster_progress (folder_path, last_run) VALUES (?, ?)",
                  (folder_path, datetime.datetime.now()))
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to mark folder as clustered: {e}")
    finally:
        conn.close()

def clear_cluster_progress():
    """
    Clears cluster progress and stacks.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM cluster_progress")
        c.execute("DELETE FROM stacks")
        c.execute("UPDATE images SET stack_id = NULL")
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to clear cluster progress: {e}")
    finally:
        conn.close()

def create_stacks_batch(stacks_data):
    """
    Creates multiple stacks and updates associations in a single transaction.
    stacks_data: list of dicts { 'name': str, 'best_image_id': int, 'image_ids': [int] }
    """
    conn = get_db()
    c = conn.cursor()
    try:
        created_count = 0
        timestamp = datetime.datetime.now()
        
        for data in stacks_data:
            # Create Stack
            c.execute("INSERT INTO stacks (name, best_image_id, created_at) VALUES (?, ?, ?)",
                      (data['name'], data['best_image_id'], timestamp))
            stack_id = c.lastrowid
            
            # Update Images
            image_ids = data['image_ids']
            if image_ids:
                # Batch update for this stack
                # "UPDATE images SET stack_id = ? WHERE id = ?"
                # We can use executemany if we flatten, but here we have varying IDs.
                # "UPDATE images SET stack_id = ? WHERE id IN (...)" is better but sqlite limit.
                # Let's use executemany with tuple list
                updates = [(stack_id, img_id) for img_id in image_ids]
                c.executemany("UPDATE images SET stack_id = ? WHERE id = ?", updates)
            
            created_count += 1
            
        conn.commit()
        return True, f"Created {created_count} stacks."
    except Exception as e:
        logging.error(f"Failed to batch create stacks: {e}")
        return False, str(e)
    finally:
        conn.close()
