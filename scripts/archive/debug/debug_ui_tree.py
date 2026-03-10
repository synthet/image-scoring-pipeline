
import os
import sys
import platform

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import db, utils, ui_tree

def print_tree(nodes, depth=0):
    for node in nodes:
        print("  " * depth + f"- {node['name']} ({node['path']})")
        if node['children']:
            print_tree(node['children'], depth + 1)

def simulate_tree_generation():
    print(f"OS: {os.name}")
    print(f"Platform: {platform.system()}")
    
    # 1. Fetch raw paths
    conn = db.get_db()
    c = conn.cursor()
    # db.get_all_folders() doesn't exist in the db.py snippet I saw?
    # I saw init_db, but not get_all_folders. Let's check db.py again or just query directly.
    # ui_tree.py uses db.get_all_folders(). Let's assume it exists or use SQL.
    # checking db.py... I didn't see it in the first 800 lines or last few lines. 
    # It might be in the middle. I'll just use SQL.
    
    try:
        # Check FOLDERS table first
        print("Checking FOLDERS table...")
        try:
            c.execute("SELECT path FROM folders")
            folders = [r[0] for r in c.fetchall()]
        except Exception as e:
            print(f"FOLDERS table query failed: {e}")
            folders = []
            
        if not folders:
            print("FOLDERS table empty or failed, checking IMAGES...")
            c.execute("SELECT FIRST 100 file_path FROM images") # Limit to avoid huge output
            paths = [r[0] for r in c.fetchall()]
            folders = list(set([os.path.dirname(p) for p in paths]))
            
        print(f"Found {len(folders)} raw folders.")
        if len(folders) > 0:
            print(f"Sample raw: {folders[0]}")
            
        # Inject problematic paths for testing
        test_paths = ['/mnt', '/mnt/', '/mnt/c', '/mnt/d', '/mnt/z', '\\mnt', '\\mnt\\d']
        print(f"Injecting test paths: {test_paths}")
        folders.extend(test_paths)
            
        # 2. Simulate ui_tree logic
        processed_folders = []
        for p in folders:
            # Simulate utils.convert_path_to_local
            local_p = utils.convert_path_to_local(p)
            if local_p:
                 # Logic from ui_tree.py
                norm = os.path.normpath(local_p)
                
                # Check filter logic
                if os.name == 'nt':
                     # Enforce drive letter Start (e.g. C:\ or D:\)
                     # This filters out \mnt, \, and relative paths
                     if len(norm) < 2 or norm[1] != ':':
                         print(f"Filtered (No Drive Letter): {norm}")
                         continue
                         
                     if norm.startswith('\\mnt') or norm == '\\':
                         print(f"Filtered (NT): {norm}")
                         continue
                else:
                     if local_p.startswith('\\'):
                         print(f"Filtered (Linux): {local_p}")
                         # continue
                
                # We want to see what WOULD be included
                processed_folders.append(local_p)

        processed_folders = list(set(processed_folders))
        print(f"Processed {len(processed_folders)} folders.")
        
        # 3. Build Tree
        roots = ui_tree.build_tree_dict(processed_folders)
        
        print("\n--- Tree Structure ---")
        print_tree(roots)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    simulate_tree_generation()
