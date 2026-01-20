import sys
import os
import argparse
import shutil
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from modules.db import get_db

def get_h_path(db_path):
    """
    Maps DB paths (WSL /mnt/d or Windows D:) to H: drive.
    """
    # Normalize slashes
    path = db_path.replace('\\', '/')
    
    # Construct H: path
    # D: maps to H:
    # So /mnt/d/Photos/... -> H:\Photos\...
    
    if path.startswith('/mnt/d/'):
        win_rel = path.replace('/mnt/d/', '').replace('/', '\\')
        return Path(r"H:\\") / win_rel
    elif path.lower().startswith('d:/'):
        win_rel = path[3:].replace('/', '\\')
        return Path(r"H:\\") / win_rel
        
    return None

def main():
    parser = argparse.ArgumentParser(description="Cleanup low score files from H: drive.")
    parser.add_argument("--delete", action="store_true", help="Actually delete files. Default is dry-run.")
    parser.add_argument("--threshold", type=float, default=0.38, help="Score threshold (exclusive). Default 0.38 (38%).")
    args = parser.parse_args()
    
    conn = get_db()
    c = conn.cursor()
    
    print(f"Querying for images with Technical < {args.threshold} OR Aesthetic < {args.threshold}...")
    
    query = """
    SELECT file_path, score_technical, score_aesthetic 
    FROM images 
    WHERE score_technical < ? OR score_aesthetic < ?
    """
    
    try:
        c.execute(query, (args.threshold, args.threshold))
        rows = c.fetchall()
        
        candidates = []
        for row in rows:
            original_path = row[0]
            # Handle tuple/Row access if needed, but fetchall returns tuples typically with this driver usage
            # modules.db might return RowWrapper. valid either way.
            # actually modules.db proxies returns RowWrapper if fetchone, but list of RowWrapper if fetchall?
            # Let's inspect inspect_scores output... "Path: ... Score: ..."
            # It accessed by index.
            
            p_tech = row[1]
            p_aes = row[2]
            
            h_path = get_h_path(original_path)
            if h_path:
                candidates.append((original_path, h_path, p_tech, p_aes))
                
        print(f"Found {len(candidates)} records matching score criteria.")
        
        files_to_delete = []
        missing_on_h = 0
        
        print("\nChecking file existence on H:...")
        for orig, dest, tech, aes in candidates:
            if dest and dest.exists():
                files_to_delete.append((dest, tech, aes))
            else:
                missing_on_h += 1
                if missing_on_h <= 10:
                    print(f"Missing (Mapped to): {dest}")
                # Optional: print(f"Missing: {dest}")
                
        print(f"Matched matched on H: drive: {len(files_to_delete)}")
        print(f"Missing from H: drive: {missing_on_h}")
        
        # Save list
        with open("low_score_files.txt", "w", encoding="utf-8") as f:
            for p, t, a in files_to_delete:
                f.write(f"{p} | T:{t:.2f} A:{a:.2f}\n")
        print("\nFull list saved to 'low_score_files.txt'")
                
        if args.delete:
            print("\n!!! DELETING FILES !!!")
            print("To cancel, press Ctrl+C immediately. Waiting 5 seconds...")
            import time
            time.sleep(5)
            
            deleted_count = 0
            errors = 0
            
            for p, t, a in files_to_delete:
                try:
                    os.remove(p)
                    # print(f"Deleted: {p}")
                    deleted_count += 1
                    if deleted_count % 100 == 0:
                        print(f"Deleted {deleted_count} files...")
                except Exception as e:
                    print(f"Failed to delete {p}: {e}")
                    errors += 1
            
            print(f"\nCompleted. Deleted: {deleted_count}. Errors: {errors}")
            
        else:
            print("\nDRY RUN COMPLETE.")
            print("Use --delete to perform actual deletion.")
            if len(files_to_delete) > 0:
                print("\nSample files that would be deleted:")
                for i in range(min(10, len(files_to_delete))):
                    print(f"{files_to_delete[i][0]} (Tech: {files_to_delete[i][1]:.2f}, Aes: {files_to_delete[i][2]:.2f})")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
