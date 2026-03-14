import os
import sys
import platform
import traceback

# Add project root to sys.path
root = r"d:\Projects\image-scoring"
if root not in sys.path:
    sys.path.append(root)

try:
    from modules import db, ui_tree, utils
    
    print(f"Platform: {platform.system()}")
    print(f"OS Name: {os.name}")
    
    # Initialize DB
    db.init_db()
    
    print("\n--- DB FOLDERS ---")
    raw_folders = db.get_all_folders()
    print(f"Raw Folders Count: {len(raw_folders)}")
    for f in raw_folders[:5]:
        print(f"  - {f}")
        
    print("\n--- CONVERSION TEST ---")
    for f in raw_folders[:5]:
        local_f = utils.convert_path_to_local(f)
        norm = os.path.normpath(local_f)
        print(f"  Raw: {f}")
        print(f"  Local: {local_f}")
        print(f"  Norm: {norm}")
        if os.name == 'nt':
            valid = len(norm) >= 2 and norm[1] == ':'
            print(f"  Valid NT: {valid}")

    print("\n--- TREE HTML GENERATION ---")
    html = ui_tree.get_tree_html()
    print(f"HTML Length: {len(html)}")
    print("HTML Preview (first 500 chars):")
    print(html[:500])
    
except Exception as e:
    print(f"\nCRITICAL ERROR: {e}")
    traceback.print_exc()
