import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from modules.db import get_db

def inspect_scores():
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Check count
        c.execute("SELECT COUNT(*) FROM images")
        count = c.fetchone()[0]
        print(f"Total images: {count}")
        
        # Check score ranges
        c.execute("SELECT MIN(score_technical), MAX(score_technical), AVG(score_technical) FROM images")
        min_s, max_s, avg_s = c.fetchone()
        print(f"Technical Score - Min: {min_s}, Max: {max_s}, Avg: {avg_s}")
        
        # Check sample paths
        c.execute("SELECT file_path, score_technical FROM images ORDER BY score_technical ASC OFFSET 0 ROWS FETCH NEXT 5 ROWS ONLY")
        rows = c.fetchall()
        print("\nLowest Scoring Samples:")
        for row in rows:
            print(f"Path: {row[0]}, Score: {row[1]}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    inspect_scores()
