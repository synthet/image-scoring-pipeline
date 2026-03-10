import os
import sys
from pathlib import Path

# Add project root to path (script is in scripts/maintenance/)
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from modules.db import get_db

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.nef', '.cr2', '.arw', '.dng', '.webp', '.heic'}

def is_image_folder(folder_path):
    try:
        if not os.path.exists(folder_path):
            return False
        with os.scandir(folder_path) as it:
            for entry in it:
                if entry.is_file():
                    _, ext = os.path.splitext(entry.name)
                    if ext.lower() in IMAGE_EXTENSIONS:
                        return True
    except Exception:
        pass
    return False

def normalize_db_path(path):
    path_lower = path.lower()
    if path_lower.startswith('/mnt/'):
        parts = path.split('/')
        if len(parts) > 2:
            drive = parts[2]
            rest = parts[3:]
            return f"{drive}:\\" + "\\".join(rest)
    return os.path.normpath(path)

def generate_report(missing_folders, output_file=None):
    if output_file is None:
        output_file = _project_root / "missing_stacks_report.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Folders Missing Stacks Report\n\n")
        f.write(f"**Total Folders Found:** {len(missing_folders)}\n\n")
        f.write("The following folders contain images but have NO stacks recorded in the database.\n\n")
        
        # Simple grouping by top-level subdir of D:\Photos
        # D:\Photos\Group\Sub...
        groups = {}
        root_prefix = r"D:\Photos"
        
        for folder in sorted(missing_folders):
            # Remove prefix
            rel_path = folder
            if folder.lower().startswith(root_prefix.lower()):
                rel_path = folder[len(root_prefix):].lstrip("\\")
            
            parts = rel_path.split("\\")
            top_group = parts[0] if parts else "Uncategorized"
            
            if top_group not in groups:
                groups[top_group] = []
            
            groups[top_group].append(rel_path)
            
        for group in sorted(groups.keys()):
            f.write(f"## {group}\n\n")
            for path in groups[group]:
                # Indent based on depth
                # path is "Group\Sub\Sub2"
                # display as:
                # - Sub\Sub2
                
                display_path = path[len(group):].lstrip("\\")
                if not display_path:
                    display_path = "."
                
                f.write(f"- `{display_path}`\n")
            f.write("\n")
            
    print(f"Report generated: {os.path.abspath(output_file)}")

def check_stacks_recursive():
    print("Fetching stack info from DB...")
    
    conn = get_db()
    cur = conn.cursor()
    
    query = """
    SELECT DISTINCT f.path
    FROM images i
    JOIN folders f ON i.folder_id = f.id
    WHERE i.stack_id IS NOT NULL
    """
    
    db_paths_with_stacks = set()
    try:
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            try:
                p = row['path'] if hasattr(row, '__getitem__') and not isinstance(row, tuple) else row[0]
            except:
                p = row[0]
            
            if p:
                win_path = normalize_db_path(str(p)).lower()
                db_paths_with_stacks.add(win_path)
    except Exception as e:
        print(f"Database error: {e}")
        return
    finally:
        conn.close()

    print(f"DB has {len(db_paths_with_stacks)} folders with stacks.")

    root_dir = r"D:\Photos"
    print(f"Scanning {root_dir} recursively for image folders...")
    
    missing_stacks_folders = []
    scanned_count = 0
    
    if os.path.exists(root_dir):
        for root, dirs, files in os.walk(root_dir):
            scanned_count += 1
            root_lower = os.path.normpath(root).lower()
            
            has_images = False
            for f in files:
                _, ext = os.path.splitext(f)
                if ext.lower() in IMAGE_EXTENSIONS:
                    has_images = True
                    break
            
            if has_images:
                if root_lower not in db_paths_with_stacks:
                    missing_stacks_folders.append(root)
                    
            if scanned_count % 2000 == 0:
                print(f"Scanned {scanned_count} folders...")
                
        generate_report(missing_stacks_folders)
    else:
        print(f"Error: {root_dir} not found.")

if __name__ == "__main__":
    check_stacks_recursive()
