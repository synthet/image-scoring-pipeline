
import sys
import os
import sqlite3

# Add current directory to path so we can import modules
sys.path.append(os.getcwd())

try:
    from modules import db
    
    # Try to get DB connection
    conn = db.get_db()
    c = conn.cursor()
    
    image_hash = 'f6a1bd2478340b6266c0d4927a7abda98e04084d8b034e24d148e717b85606a2'
    
    c.execute("SELECT file_path, file_name, model_version FROM images WHERE image_hash = ?", (image_hash,))
    row = c.fetchone()
    
    if row:
        file_path = row[0]
        file_name = row[1]
        model_ver = row[2]
        print(f"RAW_PATH: {repr(file_path)}")
        print(f"RAW_NAME: {repr(file_name)}")
        print(f"RAW_VER: {repr(model_ver)}")
    else:
        print("Image not found with that hash.")
            
    conn.close()

except Exception as e:
    print(f"Script error: {e}")
