
import sys
import os
import time

# Ensure we can import modules
sys.path.append(os.getcwd())

from modules import db, utils, ui_tree

print("--- Debugging Folder Tree ---", flush=True)

# 1. Get Raw Folders
print("Fetching folders from DB...", flush=True)
try:
    raw_folders = db.get_all_folders()
    print(f"Found {len(raw_folders)} folders in DB.", flush=True)
    for i, p in enumerate(raw_folders[:10]):
        print(f"Raw[{i}]: {repr(p)}", flush=True)
except Exception as e:
    print(f"Error fetching folders: {e}", flush=True)
    raw_folders = []

# 2. Test Conversion
print("\nTesting path conversion...", flush=True)
converted_folders = []
for p in raw_folders:
    local_p = utils.convert_path_to_local(p)
    converted_folders.append(local_p)
    if 'mnt' in p or 'mnt' in str(local_p):
         print(f"'{p}' -> '{local_p}'", flush=True)

# 3. Test Normpath & Parent
print("\nTesting Normpath & Parent...", flush=True)
nodes = {}
for i, p in enumerate(converted_folders):
    if not p: continue
    path = os.path.normpath(p)
    parent = os.path.dirname(path)
    nodes[path] = {"name": os.path.basename(path), "parent": parent}
    
    # Print suspicious ones (starting with \)
    # Check for \mnt or similar artifacts
    if path.startswith('\\mnt') or path == '\\':
        print(f"Suspicious Result: {path} | From Raw: {repr(raw_folders[i])}", flush=True)

print("--- End Debug ---", flush=True)
