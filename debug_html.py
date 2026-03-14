
import os
import sys

# Add project root to sys.path
root = r"d:\Projects\image-scoring"
if root not in sys.path:
    sys.path.append(root)

try:
    from modules import db, ui_tree, utils
    
    # Initialize DB (Windows env)
    db.init_db()
    
    html = ui_tree.get_tree_html()
    print(f"DEBUG: Generated HTML length: {len(html)}")
    
    with open("debug_tree_output.html", "w", encoding="utf-8") as f:
        f.write(html)
        
    print("DEBUG: Wrote HTML to debug_tree_output.html")
    
    # Check roots
    folders = []
    raw_folders = db.get_all_folders()
    print(f"DEBUG: Raw folders count: {len(raw_folders)}")
    for p in raw_folders:
        local_p = utils.convert_path_to_local(p)
        if local_p:
            norm = os.path.normpath(local_p)
            if os.name == 'nt':
                if len(norm) < 2 or norm[1] != ':': continue
            folders.append(local_p)
            
    folders = list(set(folders))
    print(f"DEBUG: Folders after filtering: {len(folders)}")
    
except Exception as e:
    print(f"ERROR: {e}")
