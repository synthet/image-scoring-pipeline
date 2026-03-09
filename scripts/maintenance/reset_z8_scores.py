
import logging
from modules import db

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def reset_z8_records():
    logger.info("Starting Z8 record reset...")
    
    db.init_db()
    conn = db.get_db()
    c = conn.cursor()
    
    # Check how many Z8 records exist
    c.execute("SELECT COUNT(*) FROM images WHERE file_path LIKE '%Z8%'") # Case insensitive typical in LIKE
    count = c.fetchone()[0]
    logger.info(f"Found {count} records matching '%Z8%'")
    
    if count == 0:
        logger.info("No Z8 records found to reset.")
        return

    # Update logic
    # Set scores to 0, rating to 0, label to NULL or empty, version to force update
    try:
        query = """
        UPDATE images 
        SET 
            score = 0,
            score_technical = 0,
            score_aesthetic = 0,
            score_general = 0,
            score_spaq = 0,
            score_ava = 0,
            score_koniq = 0,
            score_paq2piq = 0,
            score_liqe = 0,
            rating = 0,
            label = '',
            scores_json = '{}',
            model_version = 'RESET' 
        WHERE file_path LIKE '%Z8%'
        """
        c.execute(query)
        conn.commit()
        logger.info(f"Successfully reset {c.rowcount} records.")
        logger.info("These images should now be re-scored when you run the scoring process.")
        
    except Exception as e:
        logger.error(f"Failed to reset records: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    reset_z8_records()
