
import sys
import os
import sqlite3

# Add current directory to path so we can import modules
sys.path.append(os.getcwd())

try:
    from modules import db
    
    # Try to get DB connection
    print("Connecting to DB...")
    conn = db.get_db()
    c = conn.cursor()
    
    image_hash = 'f6a1bd2478340b6266c0d4927a7abda98e04084d8b034e24d148e717b85606a2'
    print(f"Searching for hash: {image_hash}")
    
    # We need to handle potential schema differences if get_image_by_hash is missing
    # But since we have direct SQL access, we can query safely
    query = "SELECT id, file_path, file_name, created_at, model_version FROM images WHERE image_hash = ?"
    
    try:
        c.execute(query, (image_hash,))
        row = c.fetchone()
        
        if row:
             # Handle tuple or Row object
             try:
                 # Try index access
                 print(f"Found image:\nID: {row[0]}\nPath: {row[1]}\nName: {row[2]}\nCreated: {row[3]}\nModel Version: {row[4]}")
             except:
                 # Try dict access if Row object
                 print(f"Found image: {dict(row)}")
        else:
            print("Image not found with that hash.")
            
    except Exception as e:
        print(f"Query error: {e}")
        
    conn.close()

except Exception as e:
    print(f"Script error: {e}")
    import traceback
    traceback.print_exc()
