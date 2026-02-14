import sys
import os
from pathlib import Path

# Add project root to path
project_root = str(Path(os.getcwd()).resolve())
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from modules import db
    print("Attributes of modules.db:")
    for attr in dir(db):
        if "backup" in attr.lower():
            print(f"- {attr}")
except Exception as e:
    print(f"Error: {e}")
