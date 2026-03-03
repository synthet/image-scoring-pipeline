import os
from modules.db import get_db

def _find_leaf_empty_folders(cur):
    """
    Finds folders that have NO child folders and NO images associated with them.
    We identify them by checking that their ID is not in any other folder's parent_id 
    and not in any image's folder_id.
    """
    cur.execute("""
        SELECT f.id, f.path 
        FROM folders f
        WHERE NOT EXISTS (
            SELECT 1 FROM folders child WHERE child.parent_id = f.id
        )
        AND NOT EXISTS (
            SELECT 1 FROM images i WHERE i.folder_id = f.id
        )
    """)
    return cur.fetchall()

def cleanup_empty_folders():
    con = get_db()
    cur = con.cursor()
    
    total_deleted = 0
    
    while True:
        empty_leaves = _find_leaf_empty_folders(cur)
        if not empty_leaves:
            break
            
        print(f"Found {len(empty_leaves)} empty leaf folders to remove this pass.")
        deleted_this_pass = 0
        
        for folder_id, path in empty_leaves:
            try:
                cur.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
                deleted_this_pass += 1
                if deleted_this_pass <= 5:
                    print(f"  Deleted: {path}")
            except Exception as e:
                print(f"  Failed to delete folder {folder_id} ({path}): {e}")
        
        if deleted_this_pass > 5:
            print(f"  ... and {deleted_this_pass - 5} more.")
            
        con.commit()
        total_deleted += deleted_this_pass
        
        if deleted_this_pass == 0:
            break # Avoid infinite loop if we hit constraint errors
            
    print(f"\nCleanup complete. Total empty folders removed: {total_deleted}")
    con.close()

if __name__ == "__main__":
    cleanup_empty_folders()
