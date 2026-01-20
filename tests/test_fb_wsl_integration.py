import sys
import os
sys.path.append(os.getcwd())
try:
    from modules import db
    print("Module db imported")
    
    conn = db.get_db()
    print("Connection Successful!")
    
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM images")
    row = cur.fetchone()
    print(f"Image Count: {row}")
    conn.close()
    
except Exception as e:
    print(f"Integration Error: {e}")
    import traceback
    traceback.print_exc()
