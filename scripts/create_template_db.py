
import os
import sys
import shutil

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db

def create_template():
    template_path = "template.fdb"
    if os.path.exists(template_path):
        print(f"{template_path} already exists.")
        return

    print(f"Creating fresh {template_path}...")
    
    # Temporarily point DB_PATH to template.fdb
    original_path = db.DB_PATH
    # Use local path for creation
    db.DB_FILE = template_path
    db.DB_PATH = f"inet://127.0.0.1/{os.path.abspath(template_path)}"
    
    try:
        # init_db will create the file and run DDL if it doesn't exist
        db.init_db()
        print(f"Successfully created and initialized {template_path}")
    except Exception as e:
        print(f"Failed to create template: {e}")
    finally:
        db.DB_PATH = original_path

if __name__ == "__main__":
    create_template()
