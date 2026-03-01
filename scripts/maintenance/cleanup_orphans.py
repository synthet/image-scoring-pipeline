
import os
import sys
import argparse
import logging
from pathlib import Path

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import db

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def cleanup_orphans(dry_run=True, verbose=False):
    """
    Remove orphan records from the database.
    1. Images where the file does not exist on disk.
    2. Folders that are empty (no images, no subfolders).
    """
    if dry_run:
        logger.info("Running in DRY-RUN mode. No changes will be made.")
    else:
        logger.warning("Running in LIVE mode. Changes WILL be PERMANENT.")

    conn = db.get_db()
    cursor = conn.cursor()

    try:
        # --- 1. Cleanup Orphan Images ---
        logger.info("Scanning for orphan images (missing files)...")
        
        # Fetch all images
        cursor.execute("SELECT id, file_path FROM images")
        rows = cursor.fetchall()
        
        orphan_ids = []
        checked_count = 0
        
        for row in rows:
            # Handle tuple/Row access
            if isinstance(row, tuple):
                img_id = row[0]
                file_path = row[1]
            else:
                img_id = row['id']
                file_path = row['file_path']
            
            checked_count += 1
            if not file_path:
                logger.warning(f"Image ID {img_id} has empty path. Marking for deletion.")
                orphan_ids.append(img_id)
                continue

            # Convert to Windows path if needed (logic from db.py)
            win_path = db._to_win_path(file_path)
            
            if not os.path.exists(win_path):
                if verbose:
                    logger.info(f"Missing file: {win_path} (DB: {file_path})")
                orphan_ids.append(img_id)

        logger.info(f"Checked {checked_count} images. Found {len(orphan_ids)} orphans.")

        if orphan_ids:
            if dry_run:
                logger.info(f"[DRY-RUN] Would delete {len(orphan_ids)} image records.")
            else:
                logger.info(f"Deleting {len(orphan_ids)} image records...")
                # Batch delete
                # standard SQL limit often around 999 params, chunking safely
                batch_size = 500
                for i in range(0, len(orphan_ids), batch_size):
                    batch = orphan_ids[i:i + batch_size]
                    placeholders = ','.join(['?'] * len(batch))
                    cursor.execute(f"DELETE FROM images WHERE id IN ({placeholders})", tuple(batch))
                conn.commit()
                logger.info("Deletion complete.")

        # --- 2. Cleanup Empty Folders ---
        logger.info("Scanning for empty folders...")
        
        # Helper to check if folder is empty
        def get_empty_folders():
            # Get all folders
            cursor.execute("SELECT id, path, parent_id FROM folders")
            all_folders = cursor.fetchall()
            
            # Map folder IDs to counts
            folder_map = {} # id -> {path, parent_id}
            for f in all_folders:
                if isinstance(f, tuple):
                    fid, path, pid = f
                else:
                    fid, path, pid = f['id'], f['path'], f['parent_id']
                folder_map[fid] = {'path': path, 'parent_id': pid, 'img_count': 0, 'sub_count': 0}

            # Count images per folder
            cursor.execute("SELECT folder_id, COUNT(*) FROM images GROUP BY folder_id")
            for row in cursor.fetchall():
                fid = row[0]
                count = row[1]
                if fid in folder_map: # Should be, unless FK broken
                    folder_map[fid]['img_count'] = count

            # Count subfolders
            # We can calculate this from folder_map directly
            for fid, data in folder_map.items():
                pid = data['parent_id']
                if pid and pid in folder_map:
                    folder_map[pid]['sub_count'] += 1
            
            # Find empty
            empty_ids = []
            for fid, data in folder_map.items():
                if data['img_count'] == 0 and data['sub_count'] == 0:
                    empty_ids.append(fid)
            
            return empty_ids

        # Loop until no more empty folders found (to handle nested empties)
        max_passes = 10 # Safety break
        total_folders_deleted = 0
        
        for pass_num in range(max_passes):
            empty_ids = get_empty_folders()
            if not empty_ids:
                break
                
            if verbose:
                logger.info(f"Pass {pass_num+1}: Found {len(empty_ids)} empty folders.")
            
            if dry_run:
                logger.info(f"[DRY-RUN] Would delete {len(empty_ids)} folders in pass {pass_num+1}.")
                # In dry run, we can't really simulate the cascade of empty folders without modifying structure
                # So we just report the first layer and stop or simulate?
                # Simulating is complex. Let's just report logical emptiness.
                # Actually, simply stopping is fine for dry run to show immediate candidates.
                break 
            
            # Delete
            placeholders = ','.join(['?'] * len(empty_ids))
            cursor.execute(f"DELETE FROM folders WHERE id IN ({placeholders})", tuple(empty_ids))
            conn.commit()
            total_folders_deleted += len(empty_ids)
            logger.info(f"Deleted {len(empty_ids)} folders.")
            
        if not dry_run:
            logger.info(f"Total empty folders deleted: {total_folders_deleted}")

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        conn.rollback()
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cleanup orphan DB records (images and folders).")
    parser.add_argument('--force', action='store_true', help="Execute deletions (disable dry-run)")
    parser.add_argument('--verbose', '-v', action='store_true', help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Dry run is True by default, False if --force is present
    is_dry_run = not args.force
    
    cleanup_orphans(dry_run=is_dry_run, verbose=args.verbose)
