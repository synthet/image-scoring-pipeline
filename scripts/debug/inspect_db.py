import sys
import os
from pathlib import Path

# Add project root to path (script is in scripts/debug/)
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from modules import db
    print("Attributes of modules.db:")
    for attr in dir(db):
        if "backup" in attr.lower():
            print(f"- {attr}")
except Exception as e:
    print(f"Error: {e}")
