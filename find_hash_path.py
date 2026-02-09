
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
    
    query = "SELECT id, file_path, file_name, created_at, model_version FROM images WHERE image_hash = ?"
    
    c.execute(query, (image_hash,))
    row = c.fetchone()
    
    if row:
        # Check if we can access by name or index
        try:
            # Assuming row is tuple-like
            file_path = row[1]
            print(f"Original DB Path: {file_path}")
            
            # Handle WSL paths on Windows
            if file_path.startswith('/mnt/'):
                # Convert /mnt/d/foo to D:\foo
                drive_letter = file_path[5]
                rest_of_path = file_path[7:].replace('/', '\\')
                file_path = f"{drive_letter.upper()}:\\{rest_of_path}"
                print(f"Converted Path: {file_path}")
                
            print(f"FILE_PATH: {file_path}")
            
            # Check existence
            if os.path.exists(file_path):
                print("FILE EXISTS: Yes")
            else:
                print("FILE EXISTS: No")
                
        except Exception as e:
            print(f"Error accessing row: {e}")
            print(f"Row data: {row}")
            
    else:
        print("Image not found with that hash.")
            
    conn.close()

except Exception as e:
    print(f"Script error: {e}")
    import traceback
    traceback.print_exc()
