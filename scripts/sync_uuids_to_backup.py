import os
import sys
import argparse
import subprocess
import logging
from pathlib import Path

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

def _translate_paths(db_path: str, source_root: Path, backup_root: Path) -> Path:
    local_path = normalize_db_path(db_path)
    local_path = Path(local_path)
    
    try:
        rel = local_path.relative_to(source_root)
    except ValueError:
        return None
        
    return backup_root / rel

def find_sidecar(file_path):
    base, _ = os.path.splitext(file_path)
    for ext in ['.xmp', '.XMP']:
        sidecar = base + ext
        if os.path.exists(sidecar):
            return sidecar
    return None

def sync_uuids(source="D:\\Photos", backup="E:\\Photos", dry_run=False, limit=None):
    source_root = Path(source)
    backup_root = Path(backup)
    
    if not backup_root.exists():
        logger.error(f"Backup root {backup_root} does not exist. Please connect the drive.")
        return
        
    conn = get_db()
    cur = conn.cursor()
    
    # We only care about images that already have a UUID in the database
    query = "SELECT id, file_path, image_uuid FROM images WHERE image_uuid IS NOT NULL"
    if limit:
        query += f" ROWS {limit}"
        
    try:
        cur.execute(query)
        rows = cur.fetchall()
        
        processed_count = 0
        skipped_count = 0
        error_count = 0
        
        logger.info(f"Checking {len(rows)} images with UUIDs to sync to backup.")
        
        for row in rows:
            image_id = row['id']
            db_path = str(row['file_path'])
            image_uuid = row['image_uuid']
            
            backup_path = _translate_paths(db_path, source_root, backup_root)
            
            if not backup_path or not backup_path.exists():
                logger.debug(f"Backup file not found for ID {image_id}: {backup_path}")
                skipped_count += 1
                continue
            
            backup_sidecar = find_sidecar(str(backup_path))
            
            exiftool_args = [
                'exiftool', 
                f'-ImageUniqueID={image_uuid}', 
                f'-xmp:ImageUniqueID={image_uuid}', 
                '-overwrite_original', 
                str(backup_path)
            ]
            
            if not dry_run:
                try:
                    subprocess.run(exiftool_args, capture_output=True, text=True, check=True)
                    if backup_sidecar:
                        subprocess.run([
                            'exiftool', 
                            f'-xmp:ImageUniqueID={image_uuid}', 
                            '-overwrite_original', 
                            backup_sidecar
                        ], capture_output=True, text=True, check=True)
                        logger.info(f"Updated backup ID {image_id}: {backup_path} and sidecar")
                    else:
                        logger.info(f"Updated backup ID {image_id}: {backup_path}")
                    processed_count += 1
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to update backup ID {image_id}: {e.stderr}")
                    error_count += 1
            else:
                logger.info(f"[DRY RUN] Would update backup ID {image_id}: {backup_path}")
                if backup_sidecar:
                    logger.info(f"[DRY RUN] Would update backup sidecar: {backup_sidecar}")
                processed_count += 1
                
        logger.info(f"Sync complete! Updated: {processed_count}, Skipped: {skipped_count}, Errors: {error_count}")
        
    except Exception as e:
        logger.error(f"Error reading from database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync generated UUIDs directly into backup files without re-copying huge RAW files.")
    parser.add_argument("--source", default="D:\\Photos", help="Source root mapped to backup")
    parser.add_argument("--backup", required=True, help="Backup root drive/folder (e.g. E:\\Photos)")
    parser.add_argument("--limit", type=int, help="Limit number of files to process")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without modifying files")
    
    args = parser.parse_args()
    sync_uuids(source=args.source, backup=args.backup, dry_run=args.dry_run, limit=args.limit)
