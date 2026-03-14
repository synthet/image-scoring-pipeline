
import os
import sys

# Add path
root = "/mnt/d/Projects/image-scoring"
if root not in sys.path:
    sys.path.insert(0, root)

try:
    from modules import db, ui_tree
    
    # Use real DB connection (assuming it works in WSL)
    folders = db.get_all_folders()
    print(f"Total folders from DB: {len(folders)}")
    
    # Mock filtering from ui_tree.get_tree_html
    filtered_folders = []
    for p in folders:
        # Simplified filtering for test
        if p and p not in ('/', '/mnt', '/mnt/d'):
             filtered_folders.append(p)
             
    print(f"Filtered folders: {len(filtered_folders)}")
    
    roots = ui_tree.build_tree_dict(filtered_folders)
    print(f"Roots count: {len(roots)}")
    
    def print_tree(nodes, depth=0):
        for node in nodes[:3]: # Limit to 3 per level
            print("  " * depth + f"- {node['name']} ({node['path']})")
            if node['children']:
                print_tree(node['children'], depth + 1)
        if len(nodes) > 3:
            print("  " * depth + f"... ({len(nodes) - 3} more)")

    print("\nTree Structure Preview:")
    print_tree(roots)
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
