"""
Inspect database custom utility - uses Firebird database via modules/db.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db

try:
    conn = db.get_db()
    c = conn.cursor()
    
    # Firebird: Query RDB$RELATIONS for table list
    c.execute("SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$SYSTEM_FLAG = 0")
    tables = c.fetchall()
    print("Tables:", [t[0].strip() for t in tables])

    # Firebird: Use FETCH FIRST instead of LIMIT
    c.execute("SELECT id, file_path, created_at FROM images FETCH FIRST 5 ROWS ONLY")
    rows = c.fetchall()
    print("\nSample Rows:")
    for row in rows:
        print(dict(row))
except Exception as e:
    print(f"Error reading DB: {e}")
finally:
    try:
        conn.close()
    except:
        pass
