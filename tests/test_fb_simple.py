import os
import sys

# Setup environment
fb_path = os.path.join(os.getcwd(), "Firebird")
if os.path.exists(fb_path):
    os.environ["PATH"] += ";" + fb_path
    os.environ["FIREBIRD"] = fb_path
    print(f"Set FIREBIRD={fb_path}")

from firebird.driver import create_database, connect, driver_config

# DB Path
db_path = r"C:\Users\owner\.gemini\antigravity\brain\2d85970a-6bf1-412b-a1c2-464fac53bd9e\test_migration.fdb"
if os.path.exists(db_path):
    os.unlink(db_path)

print(f"Creating DB at {db_path}")

try:
    # Attempt creation with minimal args
    create_database(db_path, user='sysdba', password='masterkey')
    print("Creation SUCCESS")
    
    con = connect(db_path, user='sysdba', password='masterkey')
    print("Connection SUCCESS")
    con.close()
    
    # Cleanup
    # os.unlink(db_path)
except Exception as e:
    print(f"FAILURE: {e}")
    import traceback
    traceback.print_exc()

# Print driver info
print(f"Driver Config: {driver_config}")
