
import os
import sys
import platform

# Add path
root = "/mnt/d/Projects/image-scoring"
if root not in sys.path:
    sys.path.insert(0, root)

try:
    from modules import db, ui_tree, utils
    
    print(f"Platform: {platform.system()}")
    print(f"OS Name: {os.name}")
    
    # Initialize DB (don't worry about re-init, it handles it)
    # But wait, we need to make sure it points to the right place.
    # config.json should be in root.
    
    raw_folders = db.get_all_folders()
    print(f"Total raw folders from DB: {len(raw_folders)}")
    
    html = ui_tree.get_tree_html()
    print(f"Generated HTML length: {len(html)}")
    
    if len(html) < 1000:
        print("HTML suspiciously short. Content:")
        print(html)
    else:
        print("HTML seems okay in length.")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
