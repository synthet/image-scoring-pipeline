
import os
import sys
import sqlite3
import logging
from modules import db, thumbnails

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fix_thumbnails():
    logger.info("Starting thumbnail repair...")
    
    # Initialize DB connection
    db.init_db()
    
    # Get all images
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT id, file_path, thumbnail_path FROM images WHERE file_path LIKE '%Z8%'")
    rows = c.fetchall()
    
    total = len(rows)
    fixed = 0
    skipped = 0
    failed = 0
    
    logger.info(f"Found {total} images in database.")
    
    for i, row in enumerate(rows):
        image_id = row['id']
        file_path = row['file_path']
        current_thumb = row['thumbnail_path']
        
        needs_regen = False
        
        # Check if original file exists
        if not os.path.exists(file_path):
            logger.warning(f"Original file missing: {file_path}")
            skipped += 1
            continue
            
        # Check if thumbnail is missing or invalid
        # Since we filtered by SQL for Z8, we force regen
        needs_regen = True
        reason = "Force Z8 Regeneration (SQL filtered)"
            
        if needs_regen:
            logger.info(f"Regenerating thumbnail for: {os.path.basename(file_path)} ({reason})")
            try:
                # Force generation logic
                # We MUST remove the existing file to force generation
                if current_thumb and os.path.exists(current_thumb):
                    try:
                        os.remove(current_thumb)
                    except OSError:
                        pass # proceed
                
                new_thumb = thumbnails.generate_thumbnail(file_path)
                
                if new_thumb and os.path.exists(new_thumb) and os.path.getsize(new_thumb) > 0:
                    # Update DB
                    c.execute("UPDATE images SET thumbnail_path = ? WHERE id = ?", (new_thumb, image_id))
                    conn.commit()
                    fixed += 1
                    logger.info(f"  ✓ Fixed: {new_thumb}")
                else:
                    logger.error(f"  ✗ Failed to generate thumbnail for {file_path}")
                    failed += 1
                    
            except Exception as e:
                logger.error(f"  Error fixing {file_path}: {e}")
                failed += 1
        else:
            skipped += 1
            
        if (i+1) % 50 == 0:
            logger.info(f"Processed {i+1}/{total}...")
            
    conn.close()
    logger.info("Thumbnail repair complete.")
    logger.info(f"Total: {total}, Fixed: {fixed}, Failed: {failed}, Skipped (OK): {skipped}")

if __name__ == "__main__":
    fix_thumbnails()
