
import sys
import os
from unittest.mock import MagicMock

# Add modules to path
sys.path.append(os.getcwd())

# Mock db module before importing ui_tree
sys.modules['modules.db'] = MagicMock()
from modules import db

# Mock utils module
sys.modules['modules.utils'] = MagicMock()
from modules import utils

# Setup mock return values
# We simulate a DB returning the unwanted folders
db.get_all_folders.return_value = [
    '/mnt/d/Photos/D90/.tmp.drivedownload',
    '/mnt/d/Photos/D90/.tmp.driveupload',
    '/mnt/d/Photos/D90/2015/keywords_output',
    '.', # The dot folder
    '/mnt/d/Photos/ValidFolder'
]

# Mock path conversion to return valid local windows paths
def mock_convert(p):
    if p.startswith('/mnt/d/'):
        return p.replace('/mnt/d/', 'D:\\').replace('/', '\\')
    return p

utils.convert_path_to_local.side_effect = mock_convert

# Import ui_tree
from modules import ui_tree

# Run the function
print("Generating Tree HTML...")
html = ui_tree.get_tree_html()

# Verify results
print("\nVerifying output:")
unwanted = ['.tmp.drivedownload', '.tmp.driveupload', 'keywords_output', '.']
path_found = False

for item in unwanted:
    # Special check for '.' in HTML might be tricky if it's just text, typically "📁 ."
    if f"📁 {item}" in html:
        print(f"FAIL: Found unwanted item '{item}' in HTML")
        path_found = True
    else:
        print(f"PASS: '{item}' correctly filtered out")

if 'ValidFolder' in html:
    print("PASS: 'ValidFolder' is present")
else:
    print("FAIL: 'ValidFolder' missing")

if not path_found:
    print("\nSUCCESS: All filters working correctly.")
else:
    print("\nFAILURE: Some filters failed.")
