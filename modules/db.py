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


def get_image_count(rating_filter=None, label_filter=None, keyword_filter=None, min_score_general=0, min_score_aesthetic=0, min_score_technical=0, date_range=None):
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
            
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    c.execute(query, tuple(params))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_images_paginated(page=1, page_size=50, sort_by="score", order="desc", rating_filter=None, label_filter=None, keyword_filter=None, min_score_general=0, min_score_aesthetic=0, min_score_technical=0, date_range=None):
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
            
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += f" ORDER BY {sort_by} {order.upper()} LIMIT ? OFFSET ?"
    params.extend([page_size, offset])
    
    c.execute(query, tuple(params))
    rows = c.fetchall()
    conn.close()
    return rows

def get_filtered_paths(rating_filter=None, label_filter=None, keyword_filter=None, min_score_general=0, min_score_aesthetic=0, min_score_technical=0, date_range=None):
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
        return True
    except Exception as e:
        logging.error(f"Failed to update path for hash {image_hash}: {e}")
        return False
    finally:
        conn.close()

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

    c.execute('''INSERT OR REPLACE INTO images 
                 (job_id, file_path, file_name, file_type, 
                  score, 
                  score_spaq, score_ava, score_koniq, score_paq2piq, score_liqe,
                  score_technical, score_aesthetic, score_general, model_version,
                  rating, label,
                  keywords, title, description, metadata, scores_json, thumbnail_path, image_hash, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (job_id, image_path, file_name, file_type, 
               score,
               score_spaq, score_ava, score_koniq, score_paq2piq, score_liqe,
               score_technical, score_aesthetic, score_general, model_version,
               rating, label,
               keywords, title, description, metadata, json.dumps(result), thumbnail_path, image_hash, datetime.datetime.now()))
    
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
