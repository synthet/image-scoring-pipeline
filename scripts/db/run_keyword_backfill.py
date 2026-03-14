import os
import sys
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import db

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def run_backfill():
    """
    Manually backfills keywords for images that have legacy keywords but are missing
    normalized entries, bypassing the existence check in db._backfill_keywords().
    """
    logger.info("Starting Keyword Backfill...")
    conn = db.get_db()
    c = conn.cursor()
    try:
        # Get images that have keywords but no entries in image_keywords
        c.execute("""
            SELECT id, keywords 
            FROM images 
            WHERE keywords IS NOT NULL AND keywords <> ''
            AND id NOT IN (SELECT DISTINCT image_id FROM image_keywords)
        """)
        rows = c.fetchall()
        logger.info(f"Found {len(rows)} images requiring backfill.")
        
        count = 0
        for row in rows:
            db._sync_image_keywords(row[0], row[1], source="manual_backfill_fix")
            count += 1
            if count % 1000 == 0:
                logger.info(f"Progress: {count}/{len(rows)}...")
        
        logger.info(f"Backfill complete. Synced {count} images.")
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_backfill()
