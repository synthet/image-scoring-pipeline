
import sys
import os
from pathlib import Path

# Add project root (directory of this script) to path
project_root = str(Path(__file__).resolve().parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from modules import db

def diagnose():
    print(f"Diagnosing low general scores and mismatches from {project_root}...")
    try:
        conn = db.get_db()
        cursor = conn.cursor()
        
        # Check low general scores
        query_low = """
        SELECT COUNT(*) 
        FROM images 
        WHERE score_general > 0 AND score_general < 0.01
        """
        cursor.execute(query_low)
        low_count = cursor.fetchone()[0]
        print(f"Found {low_count} images with score_general between 0 and 0.01.")
        
        if low_count > 0:
             cursor.execute("""
             SELECT FIRST 5 id, file_name, score_general, score_technical, score_aesthetic 
             FROM images WHERE score_general > 0 AND score_general < 0.01
             """)
             print("Sample low scores:", cursor.fetchall())

        # Check for Technical != LIQE mismatch (assuming normalized LIQE)
        # Note: LIQE in DB might be raw > 1.0. Tech should be normalized.
        # So we check if Tech is significantly different from normalized LIQE.
        # Or simply check consistency.
        
        # Check count where Tech/Aes are OLD (based on previous observations?)
        # Let's check generally if Tech seems to match LIQE
        print("\nchecking Tech vs LIQE consistency...")
        cursor.execute("""
        SELECT FIRST 5 id, score_technical, score_liqe FROM images 
        WHERE score_liqe IS NOT NULL AND score_technical IS NOT NULL
        """)
        rows = cursor.fetchall()
        for row in rows:
            print(f"ID: {row[0]}, Tech: {row[1]}, LIQE: {row[2]}")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    diagnose()
