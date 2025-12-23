
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from modules import db

output_file = "test_export.json"

if os.path.exists(output_file):
    os.remove(output_file)

print("Testing export_db_to_json...")
success, msg = db.export_db_to_json(output_file)

print(f"Success: {success}")
print(f"Message: {msg}")

if success and os.path.exists(output_file):
    print("Verification PASSED: File created.")
    # Validation
    import json
    with open(output_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        print(f"Record count: {len(data)}")
else:
    print("Verification FAILED.")
