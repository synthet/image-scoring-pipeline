import sys
import os
import numpy as np
from pathlib import Path

# Add project root to path (script is in scripts/archive/)
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from modules.db import get_db
from modules.diversity import reorder_with_mmr

def main():
    print("Connecting to DB...")
    conn = get_db()
    cur = conn.cursor()
    
    print("Fetching top 50 images from folder ID 692...")
    cur.execute('''
        SELECT FIRST 50 ID, FILE_PATH, SCORE_GENERAL, IMAGE_EMBEDDING 
        FROM IMAGES 
        WHERE FOLDER_ID = 692 AND SCORE_GENERAL IS NOT NULL AND IMAGE_EMBEDDING IS NOT NULL
        ORDER BY SCORE_GENERAL DESC
    ''')
    
    rows = cur.fetchall()
    print(f"Found {len(rows)} images.")
    
    sorted_images = []
    embeddings_dict = {}
    
    for row in rows:
        img_id, path, score, emb_blob = row
        sorted_images.append({
            "id": img_id,
            "path": path,
            "score_general": score
        })
        if emb_blob:
            try:
                # If it's a blob reader object
                embeddings_dict[img_id] = emb_blob.read()
            except AttributeError:
                # If it's already bytes
                embeddings_dict[img_id] = emb_blob
                
    conn.close()
    
    picked = reorder_with_mmr(sorted_images, k=10, embeddings_dict=embeddings_dict, lambda_val=0.5)
    
    out_lines = []
    out_lines.append("Top 10 Diverse High-Scoring Images:")
    for i, img in enumerate(picked[:10]):
        path = img['path']
        if path.startswith("/mnt/") and len(path) > 7 and path[6] == "/":
            path = path[5].upper() + ":\\" + path[7:].replace("/", "\\")
        out_lines.append(f"{i+1}. Score: {img['score_general']:.4f} | Path: {path}")
    
    result_text = "\n".join(out_lines)
    print("\n" + result_text)
    
    # Also write to a file to easily read the output
    out_file = Path(__file__).resolve().parents[2] / "diverse_picks.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(result_text)
    print(f"Wrote {out_file}")

if __name__ == "__main__":
    main()
