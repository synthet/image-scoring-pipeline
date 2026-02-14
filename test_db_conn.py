
import sys
import os
from pathlib import Path

# Add project root
project_root = str(Path(__file__).resolve().parent)
if project_root not in sys.path:
    sys.path.append(project_root)

print(f"Project root: {project_root}")

try:
    from modules import db
    print("Imported modules.db")
    
    # Force localhost TCP connection
    db_path = db.DB_PATH
    print(f"Original DB Path: {db_path}")
    
    # Try connecting using localhost prefix to force TCP/IP and use the running server
    # This avoids "file in use" errors if the server is running
    dsn = f"localhost:{db_path}"
    print(f"Connecting to: {dsn}")
    
    # Pass DSN as positional arg (first arg)
    conn = db.connect(dsn, user=db.DB_USER, password=db.DB_PASS)
    print("Got DB connection via connect()")

    
    c = conn.cursor()
    c.execute("SELECT count(*) FROM images")
    row = c.fetchone()
    print(f"Image count: {row[0]}")
    
    conn.close()
    print("Success")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
