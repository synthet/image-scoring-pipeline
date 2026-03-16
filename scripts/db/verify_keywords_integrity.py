import os
import sys
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import db

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def verify_keywords_integrity():
    """
    Compares legacy IMAGES.KEYWORDS (CSV string) with normalized 
    IMAGE_KEYWORDS table to ensure dual-write is consistent.
    """
    logger.info("Starting Keyword Integrity Check...")
    
    conn = db.get_db()
    c = conn.cursor()
    
    try:
        # 1. Get all images with legacy keywords
        c.execute("SELECT id, file_path, keywords FROM images WHERE keywords IS NOT NULL AND keywords <> ''")
        legacy_rows = c.fetchall()
        
        mismatches = []
        missing_normalized = []
        total_checked = 0
        
        for row in legacy_rows:
            image_id, file_path, legacy_val = row
            total_checked += 1
            
            # Normalize legacy list
            legacy_set = set(k.strip().lower() for k in legacy_val.split(',') if k.strip())
            
            # Get normalized keywords
            c.execute("""
                SELECT kd.keyword_norm 
                FROM image_keywords ik
                JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
                WHERE ik.image_id = ?
            """, (image_id,))
            norm_rows = c.fetchall()
            norm_set = set(r[0] for r in norm_rows)
            
            if not norm_set and legacy_set:
                missing_normalized.append((image_id, file_path))
            elif legacy_set != norm_set:
                mismatches.append({
                    "id": image_id,
                    "path": file_path,
                    "legacy": sorted(list(legacy_set)),
                    "normalized": sorted(list(norm_set)),
                    "extra_in_legacy": sorted(list(legacy_set - norm_set)),
                    "extra_in_normalized": sorted(list(norm_set - legacy_set))
                })

        # 2. Results
        logger.info(f"Checked {total_checked} images.")
        
        if not mismatches and not missing_normalized:
            logger.info("✅ SUCCESS: Keyword integrity verified. Legacy and normalized data match perfectly.")
        else:
            if missing_normalized:
                logger.warning(f"❌ Found {len(missing_normalized)} images missing normalized keyword rows entirely.")
                for img_id, path in missing_normalized[:10]:
                    logger.debug(f"  Missing: ID {img_id} - {path}")
            
            if mismatches:
                logger.warning(f"❌ Found {len(mismatches)} images with keyword mismatches.")
                for m in mismatches[:5]:
                    logger.info(f"  ID {m['id']}: {os.path.basename(m['path'])}")
                    logger.info(f"    Legacy: {m['legacy']}")
                    logger.info(f"    Norm:   {m['normalized']}")
            
            logger.info("\nRun db._backfill_keywords() if significant data is missing.")
            
    except Exception as e:
        logger.error(f"Verification failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    verify_keywords_integrity()
