
import os
import sys

# Add project root to python path to allow importing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import db

def cleanup_windows_paths():
    """
    Remove records from the images table that have Windows-style paths (e.g. 'D:\...')
    instead of WSL-style paths ('/mnt/d/...').
    """
    conn = db.get_db()
    cursor = conn.cursor()

    try:
        # 1. Identify records to be deleted for logging
        print("Searching for records with Windows-style paths...")
        # Searching for paths matching Pattern "X:\%" (e.g. C:\, D:\)
        # Using a more generic LIKE pattern to catch single letter drives
        cursor.execute("SELECT id, file_path, score_general FROM images WHERE file_path LIKE '_:\%'")
        rows = cursor.fetchall()

        if not rows:
            print("No Windows-style paths found. Database is clean.")
            return

        print(f"Found {len(rows)} records with Windows-style paths:")
        ids_to_delete = []
        for row in rows:
            # Handle tuple or Row object
            if isinstance(row, tuple):
                rec_id = row[0]
                path = row[1]
                score = row[2]
            else:
                rec_id = row['id']
                path = row['file_path']
                score = row['score_general']
            
            print(f"  - ID: {rec_id}, Path: {path}, Score: {score}")
            ids_to_delete.append(rec_id)

        # 2. Delete the records
        if ids_to_delete:
            print(f"\nDeleting {len(ids_to_delete)} records...")
            
            # Construct parameterized query for safety
            placeholders = ','.join(['?'] * len(ids_to_delete))
            delete_query = f"DELETE FROM images WHERE id IN ({placeholders})"
            
            cursor.execute(delete_query, tuple(ids_to_delete))
            conn.commit()
            print("Deletion complete and committed.")
            
            # 3. Verification
            cursor.execute("SELECT COUNT(*) FROM images WHERE file_path LIKE '_:\%'")
            count = cursor.fetchall()[0][0]
            if count == 0:
                print("Verification successful: No Windows-style paths remain.")
            else:
                print(f"WARNING: Verification failed. {count} records still remain.")
        
    except Exception as e:
        print(f"Error during cleanup: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    cleanup_windows_paths()
