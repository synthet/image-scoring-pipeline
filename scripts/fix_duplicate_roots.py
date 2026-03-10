
import sys
import os
import logging
import time

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fix_roots_retry")

def cleanup_roots():
    logger.info("Starting cleanup of roots with retry...")
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            conn = db.get_db()
            c = conn.cursor()
            
            # 2. Merge Duplicates (Normalization)
            logger.info("Checking for duplicates via normalization...")
            
            # Get ALL folders to build a map of normalized_path -> id
            c.execute("SELECT id, path FROM folders")
            all_folders = c.fetchall()
            
            norm_map = {} # normalized_path -> id (first one encountered, or prefer one with parent?)
            
            # We want to prefer the "cleanest" one.
            # Heuristic: Prefer one without trailing slash, prefer one with forward slashes if that's dominant.
            # Actually, let's just find duplicates first.
            
            # Sort by ID to keep oldest? Or Sort by path length?
            # Let's sort by ID.
            all_folders.sort(key=lambda x: x[0])
            
            duplicates = [] # list of (id_to_remove, id_to_keep)
            
            for fid, fpath in all_folders:
                # Normalize:
                # 1. Replace \ with /
                # 2. Strip trailing / (unless it is just /)
                norm = fpath.replace('\\', '/')
                if len(norm) > 1:
                    norm = norm.rstrip('/')
                
                if norm in norm_map:
                    keep_id = norm_map[norm]
                    if keep_id != fid:
                        duplicates.append((fid, keep_id, fpath))
                else:
                    norm_map[norm] = fid
                    
            logger.info(f"Found {len(duplicates)} duplicates to merge.")
            
            for dup in duplicates:
                remove_id = dup[0]
                keep_id = dup[1]
                orig_path = dup[2]
                
                logger.info(f"  - Merging ID={remove_id} ('{orig_path}') into ID={keep_id}")
                
                # Move children folders
                c.execute("UPDATE folders SET parent_id = ? WHERE parent_id = ?", (keep_id, remove_id))
                # Move images
                c.execute("UPDATE images SET folder_id = ? WHERE folder_id = ?", (keep_id, remove_id))
                # Delete folder
                c.execute("DELETE FROM folders WHERE id = ?", (remove_id,))
                
            conn.commit()
            
            logger.info("Cleanup successful.")
            return

        except Exception as e:
            logger.error(f"Attempt {attempt+1} failed: {e}")
            try: conn.close()
            except: pass
            time.sleep(2)
            
    logger.error("Failed after retries.")

if __name__ == "__main__":
    cleanup_roots()
