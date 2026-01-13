
import os
import platform
import re

# Mock utils.convert_path_to_local
def convert_path_to_local(path):
    system = "Windows" # Force Windows for repro
    
    if system == "Windows":
        # Handle WSL paths
        if path.startswith("/mnt/"):
            # /mnt/d/Description -> D:/Description
            parts = path.split('/')
            if len(parts) > 2 and len(parts[2]) == 1:
                drive = parts[2].upper()
                rest = "/".join(parts[3:])
                return f"{drive}:/{rest}"
    elif system == "Linux":
         match = re.match(r'^([a-zA-Z]):[\\\/](.*)', path)
         if match:
             drive = match.group(1).lower()
             rest = match.group(2).replace('\\', '/')
             return f"/mnt/{drive}/{rest}"
    
    return path

# Mock ui_tree.build_tree_dict
def build_tree_dict(paths):
    # Sort paths
    paths = sorted(paths)
    nodes = {}
    roots = []
    
    for path in paths:
        path = os.path.normpath(path)
        parent = os.path.dirname(path)
        
        node = {"name": os.path.basename(path) if os.path.basename(path) else path, "path": path, "children": []}
        nodes[path] = node
        
        if parent == path or not parent: # Root
             roots.append(node)
        elif parent in nodes:
             nodes[parent]["children"].append(node)
        else:
             print(f"Orphaned node found (parent not in nodes): {path}, Parent: {parent}")
             roots.append(node)
    
    return roots

def print_tree(nodes, prefix=""):
    for node in nodes:
        print(f"{prefix}{node['name']}")
        print_tree(node['children'], prefix + "  ")

# Simulated DB paths
raw_folders = [
    "/",
    "/mnt",
    "/mnt/d",
    "/mnt/d/Photos",
    "/mnt/d/Photos/Z8",
    "/mnt/d/Photos/Z8/180-600mm",
    "/mnt/d/Photos/Z8/180-600mm/2025"
]

print("--- Simulating Tree Building on Windows ---")
folders = []
for p in raw_folders:
    local_p = convert_path_to_local(p)
    if local_p:
        print(f"Original: {p} -> Local: {local_p}")
        folders.append(local_p)

folders = list(set(folders))
roots = build_tree_dict(folders)

print("\n--- Resulting Tree ---")
print_tree(roots)
