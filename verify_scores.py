
import sys
import os
from pathlib import Path
from modules import db

# Ensure project root in path
project_root = str(Path(__file__).resolve().parent)
if project_root not in sys.path:
    sys.path.append(project_root)

def verify():
    # Force localhost TCP
    dsn = f"localhost:{db.DB_PATH}"
    print(f"Connecting to {dsn}...")
    try:
        conn = db.connect(dsn, user=db.DB_USER, password=db.DB_PASS)
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    c = conn.cursor()
    
    # Check total count
    c.execute("SELECT count(*) FROM images")
    total = c.fetchone()[0]
    print(f"Total images: {total}")
    
    # Check tiny scores (< 0.1)
    c.execute("SELECT count(*) FROM images WHERE score_general < 0.1 AND score_general > 0")
    tiny_count = c.fetchone()[0]
    print(f"Tiny scores (< 0.1): {tiny_count}")
    
    if tiny_count > 0:
        print("FAIL: Still have tiny scores. Listing first 5:")
        c.execute("SELECT id, score_general, score_liqe, score_ava, score_spaq FROM images WHERE score_general < 0.1 AND score_general > 0 FETCH FIRST 5 ROWS ONLY")
        rows = c.fetchall()
        for r in rows:
            print(f"ID {r[0]}: Gen {r[1]}, LIQE {r[2]}, AVA {r[3]}, SPAQ {r[4]}")
    else:
        print("PASS: No tiny scores found.")
        
    # Check average score
    c.execute("SELECT AVG(score_general) FROM images")
    avg = c.fetchone()[0]
    print(f"Average General Score: {avg:.4f}")
    
    conn.close()

if __name__ == "__main__":
    verify()
