"""
Check database utility - uses Firebird database via modules/db.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import db

try:
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM images")
    count = c.fetchone()[0]
    print(f"Total images in DB: {count}")
    
    # Firebird: Use FETCH FIRST instead of LIMIT
    c.execute("SELECT * FROM images FETCH FIRST 5 ROWS ONLY")
    rows = c.fetchall()
    print("First 5 records:")
    for r in rows:
        print(dict(r))
        
    conn.close()
except Exception as e:
    print(f"Error reading DB: {e}")
