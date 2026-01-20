import os
import sys

# Mock os.name if needed, but we expect it to be passed by the system.
print(f"OS Name: {os.name}")
print(f"Platform: {sys.platform}")

# Mock modules
class MockUtils:
    def convert_path_to_local(self, path):
        # Copy of logic from utils.py
        import platform
        system = "Windows" # Force Windows logic for repro
        
        if system == "Windows":
            p_str = path.replace('\\', '/')
            if p_str.startswith("/mnt/"):
                parts = p_str.split('/')
                if len(parts) > 2 and len(parts[2]) == 1:
                    drive = parts[2].upper()
                    rest = "/".join(parts[3:])
                    return f"{drive}:/{rest}"
        return path

utils = MockUtils()

def build_tree_dict(paths):
    paths = sorted(paths)
    nodes = {}
    roots = []
    
    for path in paths:
        path = os.path.normpath(path)
        parent = os.path.dirname(path)
        
        node = {"name": os.path.basename(path) if os.path.basename(path) else path, "path": path, "children": []}
        nodes[path] = node
        
        if parent == path or not parent: 
             roots.append(node)
        elif parent in nodes:
             nodes[parent]["children"].append(node)
        else:
             roots.append(node)
    
    return roots

def test_logic():
    # Mock data from DB (likely WSL paths)
    raw_folders = [
        "/mnt/d/Photos",
        "/mnt/d/Photos/Z8",
        "/mnt/d", 
        "/mnt", 
        "/"
    ]
    
    print("Raw Folders:", raw_folders)
    
    folders = []
    for p in raw_folders:
        local_p = utils.convert_path_to_local(p)
        print(f"'{p}' -> '{local_p}'")
        
        if local_p:
            # logic from ui_tree.py
            # Force os.name check simulation
            if True: # os.name == 'nt' simulation
                 norm = os.path.normpath(local_p)
                 print(f"  Norm: '{norm}'")
                 if norm.startswith('\\mnt') or norm == '\\':
                     print("  -> FILTERED")
                     continue
            folders.append(local_p)
            
    # Remove duplicates
    folders = list(set(folders))
    print("\nFinal Folders List:", folders)
    
    roots = build_tree_dict(folders)
    
    def print_tree(nodes, indent=0):
        for node in nodes:
            print("  " * indent + f"- {node['name']} ({node['path']})")
            print_tree(node['children'], indent + 1)

    print("\nTree Structure:")
    print_tree(roots)

if __name__ == "__main__":
    test_logic()
