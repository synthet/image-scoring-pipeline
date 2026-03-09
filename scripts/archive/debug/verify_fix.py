import sys
import os
sys.path.append(os.getcwd())

try:
    from modules import db
    print("Successfully imported db module")
except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)

print("Calling init_db() with retry logic...")
try:
    db.init_db()
    print("init_db() completed successfully.")
except Exception as e:
    print(f"init_db() failed with error: {e}")
