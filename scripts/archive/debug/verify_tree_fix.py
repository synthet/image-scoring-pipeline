import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from modules import utils
from modules import ui_tree

# Mock DB return
def mock_get_all_folders():
    return [
        "/mnt/d/Photos",
        "/mnt/d/Photos/Z8",
        "/mnt/d", 
        "/mnt", 
        "/"
    ]

# Monkeypatch db
class MockDB:
    def get_all_folders(self):
        return mock_get_all_folders()

ui_tree.db = MockDB()

print("Testing get_tree_html logic with real modules...")
html = ui_tree.get_tree_html()
print("HTML Generated (First 500 chars):")
print(html[:500])

# Check for presence of "mnt" or "\" artifacts
if "mnt" in html and "class=\"tree-content\">📁 mnt" in html:
    print("FAILURE: 'mnt' folder found in tree.")
else:
    print("SUCCESS: 'mnt' folder NOT found in tree.")

if "class=\"tree-content\">📁 \\" in html:
    print("FAILURE: '\\' artifact found in tree.")
else:
    print("SUCCESS: '\\' artifact NOT found in tree.")
