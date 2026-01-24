"""
Check database and folder associations - uses Firebird database via modules/db.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db

target_path = r'D:\Photos\Z8\180-600mm\2025\2025-12-28'

print(f"Checking Firebird database")
print(f"Target path: {target_path}")

try:
    conn = db.get_db()
    c = conn.cursor()
    
    # Check total images
    c.execute("SELECT COUNT(*) FROM images")
    total = c.fetchone()[0]
    print(f"Total images in DB: {total}")
    
    # Check images in specific folder
    # Use both backslashes and forward slashes just in case
    c.execute("SELECT COUNT(*) FROM images WHERE file_path LIKE ?", (target_path + '%',))
    count = c.fetchone()[0]
    print(f"Images in folder (exact match): {count}")
    
    # Case insensitive check or path normalization check
    target_norm = target_path.replace('\\', '/')
    c.execute("SELECT COUNT(*) FROM images WHERE file_path LIKE ?", (target_norm + '%',))
    count_forward = c.fetchone()[0]
    print(f"Images in folder (forward slash): {count_forward}")
    
    # Check folders table - Firebird: Use FETCH FIRST instead of LIMIT
    c.execute("SELECT id, path FROM folders FETCH FIRST 10 ROWS ONLY")
    rows = c.fetchall()
    print("\nExample folders in DB:")
    for row in rows:
        print(f"  ID: {row['id']}, Path: {row['path']}")
    
    # Try to find target folder using partial match
    print(f"\nSearching for folder containing '2025-12-28':")
    c.execute("SELECT id, path FROM folders WHERE path LIKE '%2025-12-28%'")
    rows = c.fetchall()
    for row in rows:
        print(f"  Found: ID={row['id']}, Path={row['path']}")
        
    # Check image count for EACH found folder ID
        c.execute("SELECT COUNT(*) FROM images WHERE folder_id = ?", (row['id'],))
        img_count = c.fetchone()[0]
        print(f"    -> Images with this folder_id: {img_count}")
        
    print("\nTesting get_or_create_folder logic via db.py:")
    windows_path = r'D:\Photos\Z8\180-600mm\2025\2025-12-28'
    print(f"  Input Windows Path: {windows_path}")
    fid = db.get_or_create_folder(windows_path)
    print(f"  Returned Folder ID: {fid}")
    
    # Verify what path corresponds to this ID
    c.execute("SELECT path FROM folders WHERE id = ?", (fid,))
    row = c.fetchone()
    if row:
        print(f"  Path in DB for ID {fid}: {row['path']}")
    
    # Check if this ID has images
    c.execute("SELECT COUNT(*) FROM images WHERE folder_id = ?", (fid,))
    count = c.fetchone()[0]
    print(f"  Images associated with this ID: {count}")

    conn.close()
except Exception as e:
    print(f"Error: {e}")
