"""Query database for cleanup planning - write to file."""
from modules.db import get_db

conn = get_db()
cur = conn.cursor()

with open("cleanup_report.txt", "w") as f:
    f.write("=== LABEL DISTRIBUTION ===\n")
    cur.execute("SELECT label, COUNT(*) FROM images GROUP BY label")
    for row in cur.fetchall():
        f.write(f"  {row[0]}: {row[1]}\n")

    f.write("\n=== CULL_DECISION DISTRIBUTION ===\n")
    cur.execute("SELECT CULL_DECISION, COUNT(*) FROM images GROUP BY CULL_DECISION")
    for row in cur.fetchall():
        f.write(f"  '{row[0]}': {row[1]}\n")

    # Rejected
    cur.execute("SELECT COUNT(*) FROM images WHERE CULL_DECISION = 'reject'")
    rejected_count = cur.fetchone()[0]
    f.write(f"\n=== REJECTED FILES (cull_decision='reject'): {rejected_count} ===\n")
    
    # Red
    cur.execute("SELECT COUNT(*) FROM images WHERE label = 'Red'")
    red_count = cur.fetchone()[0]
    f.write(f"\n=== RED LABELED: {red_count} ===\n")
    
    # Overlap
    cur.execute("SELECT COUNT(*) FROM images WHERE label = 'Red' AND CULL_DECISION = 'reject'")
    overlap = cur.fetchone()[0]
    f.write(f"\n=== OVERLAP (Red AND rejected): {overlap} ===\n")
    
    # Union (total to delete)
    cur.execute("SELECT COUNT(*) FROM images WHERE label = 'Red' OR CULL_DECISION = 'reject'")
    union = cur.fetchone()[0]
    f.write(f"\n=== UNION (Red OR rejected): {union} ===\n")

    # Sample rejected paths
    f.write("\n=== Sample REJECTED file paths (first 20) ===\n")
    cur.execute("SELECT FIRST 20 file_path FROM images WHERE CULL_DECISION = 'reject'")
    for row in cur.fetchall():
        f.write(f"  {row[0]}\n")

    # Sample Red paths
    f.write("\n=== Sample RED file paths (first 20) ===\n")
    cur.execute("SELECT FIRST 20 file_path FROM images WHERE label = 'Red'")
    for row in cur.fetchall():
        f.write(f"  {row[0]}\n")

    # Path format samples
    f.write("\n=== GENERAL PATH FORMAT SAMPLES ===\n")
    cur.execute("SELECT FIRST 5 file_path FROM images")
    for row in cur.fetchall():
        f.write(f"  {row[0]}\n")

conn.close()
print("Report written to cleanup_report.txt")
