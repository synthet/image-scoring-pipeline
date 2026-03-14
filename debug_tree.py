import os
import sys
# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules import db, ui_tree

# Initialize DB
db.init_db()

print("--- RAW FOLDERS ---")
raw_folders = db.get_all_folders()
print(raw_folders)

print("\n--- TREE HTML ---")
html = ui_tree.get_tree_html()
print(html)
