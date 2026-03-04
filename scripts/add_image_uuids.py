import os
import sys
import uuid
import subprocess
import argparse
import logging

# Add project root to path
sys.path.append(os.getcwd())

from modules.db import get_db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def normalize_db_path(path):
    path_lower = path.lower()
    if path_lower.startswith('/mnt/'):
        parts = path.split('/')
        if len(parts) > 2:
            drive = parts[2]
            rest = parts[3:]
            return f"{drive}:\\" + "\\".join(rest)
    return os.path.normpath(path)

def find_sidecar(file_path):
    """Find the corresponding XMP sidecar file if it exists."""
    base, _ = os.path.splitext(file_path)
    for ext in ['.xmp', '.XMP']:
        sidecar = base + ext
        if os.path.exists(sidecar):
            return sidecar
    return None

def process_images(dry_run=False, limit=None, specific_id=None):
    conn = get_db()
    cur = conn.cursor()

    query = "SELECT id, file_path, file_name, image_uuid FROM images WHERE image_uuid IS NULL AND file_path IS NOT NULL"
    params = []
    
    if specific_id:
        query = "SELECT id, file_path, file_name, image_uuid FROM images WHERE id = ? AND file_path IS NOT NULL"
        params = [specific_id]
        
    if limit:
        query += f" ROWS {limit}"
        
    try:
        cur.execute(query, params)
        rows = cur.fetchall()
        
        if not rows:
            logger.info("No images found needing a UUID.")
            return

        logger.info(f"Found {len(rows)} images to process.")
        
        processed_count = 0
        skipped_count = 0
        error_count = 0
        
        for row in rows:
            image_id = row['id']
            file_path = normalize_db_path(row['file_path'])
            
            if not os.path.exists(file_path):
                logger.warning(f"File not found, skipping ID {image_id}: {file_path}")
                skipped_count += 1
                continue
                
            new_uuid = str(uuid.uuid4())
            sidecar_path = find_sidecar(file_path)
            
            # ExifTool command to update the image file
            exiftool_args = [
                'exiftool',
                f'-ImageUniqueID={new_uuid}',
                f'-xmp:ImageUniqueID={new_uuid}',
                '-overwrite_original',
                file_path
            ]
            
            logger.info(f"Processing ID {image_id}: {file_path} -> {new_uuid}")
            
            if not dry_run:
                try:
                    # Run exiftool on the image
                    result = subprocess.run(exiftool_args, capture_output=True, text=True, check=True)
                    
                    # If sidecar exists, run exiftool on it too
                    if sidecar_path:
                        exiftool_sidecar_args = [
                            'exiftool',
                            f'-xmp:ImageUniqueID={new_uuid}',
                            '-overwrite_original',
                            sidecar_path
                        ]
                        logger.info(f"  Updating sidecar: {sidecar_path}")
                        subprocess.run(exiftool_sidecar_args, capture_output=True, text=True, check=True)
                    
                    # Update database
                    update_query = "UPDATE images SET image_uuid = ? WHERE id = ?"
                    cur.execute(update_query, [new_uuid, image_id])
                    conn.commit()
                    
                    processed_count += 1
                except subprocess.CalledProcessError as e:
                    logger.error(f"ExifTool failed for ID {image_id}: {e.stderr}")
                    error_count += 1
                except Exception as e:
                    logger.error(f"Error processing ID {image_id}: {e}")
                    conn.rollback()
                    error_count += 1
            else:
                logger.info(f"  [DRY RUN] Would execute: {' '.join(exiftool_args)}")
                if sidecar_path:
                    logger.info(f"  [DRY RUN] Would update sidecar: {sidecar_path}")
                processed_count += 1
                
        logger.info(f"Complete! Processed: {processed_count}, Skipped: {skipped_count}, Errors: {error_count}")

    except Exception as e:
        logger.error(f"Database error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate and embed UUIDs for images.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing them")
    parser.add_argument("--limit", type=int, help="Limit the number of images to process")
    parser.add_argument("--id", type=int, help="Process a specific image ID")
    
    args = parser.parse_args()
    process_images(dry_run=args.dry_run, limit=args.limit, specific_id=args.id)
