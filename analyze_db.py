
import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from modules.db import get_db

def to_windows_path(path):
    if not path: return None
    if path.startswith("/mnt/"):
        # /mnt/d/Foo -> D:/Foo
        parts = path.split("/")
        if len(parts) > 2:
            drive = parts[2]
            rest = "/".join(parts[3:])
            return f"{drive.upper()}:/{rest}"
    return path

def analyze():
    print("Analyzing Database Health (WSL Aware)...")
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM images")
    rows = c.fetchall()
    
    total = len(rows)
    healthy = 0
    fixable_paths = 0
    truly_corrupted = []
    
    print(f"Total Rows: {total}")
    print("-" * 30)
    
    for row in rows:
        issues = []
        path_fixable = False
        
        # 1. Check Image File
        file_path = row['file_path']
        if not file_path or not os.path.exists(file_path):
            # Try converting
            win_path = to_windows_path(file_path)
            if win_path and os.path.exists(win_path):
                path_fixable = True
            else:
                issues.append(f"Image Missing: {file_path}")
            
        # 2. Check Thumbnail
        thumb_path = row['thumbnail_path']
        if not thumb_path:
            issues.append("Thumbnail value is NULL/Empty")
        elif not os.path.exists(thumb_path):
             win_thumb = to_windows_path(thumb_path)
             if win_thumb and os.path.exists(win_thumb):
                 path_fixable = True
             else:
                 issues.append(f"Thumbnail File Missing: {thumb_path}")
            
        # 3. Check JSON validity
        json_str = row['scores_json']
        try:
            if json_str:
                json.loads(json_str)
        except:
            issues.append("Invalid JSON data")
            
        # 4. Check Score
        score = row['score']
        if score is None:
            issues.append("Score is NULL")
            
        if issues:
            truly_corrupted.append({
                "id": row['id'],
                "file": file_path,
                "issues": issues
            })
        elif path_fixable:
            fixable_paths += 1
        else:
            healthy += 1
            
    conn.close()
    
    print(f"Healthy Records (Valid Paths): {healthy}")
    print(f"Fixable Records (WSL Paths): {fixable_paths}")
    print(f"Truly Corrupted Records: {len(truly_corrupted)}")
    print("-" * 30)
    
    if truly_corrupted:
        print("Corruption Details (First 10):")
        for bad in truly_corrupted[:10]:
            print(f"ID {bad['id']}: {', '.join(bad['issues'])}")
            
        if len(corrupted) > 10:
            print(f"... and {len(corrupted) - 10} more.")
            
    return len(corrupted)

if __name__ == "__main__":
    analyze()
