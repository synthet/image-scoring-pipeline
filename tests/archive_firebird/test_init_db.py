import os
import sys
import shutil
import uuid

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db
from firebird.driver import driver_config

# Config
fb_dll = os.path.abspath(os.path.join(os.path.dirname(db.__file__), "..", "Firebird", "fbclient.dll"))
if hasattr(driver_config, 'fb_client_library') and os.path.exists(fb_dll):
    driver_config.fb_client_library.value = fb_dll
    print(f"Configured FB driver: {fb_dll}")

DB_DIR = os.path.abspath("temp_test_init")
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

TEST_DB_PATH = os.path.join(DB_DIR, f"test_init_{uuid.uuid4().hex}.fdb")
TEMPLATE_PATH = os.path.abspath("template.fdb")

def test_manual_init():
    if not os.path.exists(TEMPLATE_PATH):
        print("Template missing")
        return

    shutil.copy2(TEMPLATE_PATH, TEST_DB_PATH)
    print(f"DB Copy: {TEST_DB_PATH}")
    
    # TCP Connection
    db.DB_PATH = f"inet://127.0.0.1/{TEST_DB_PATH}"
    print(f"DSN: {db.DB_PATH}")
    
    try:
        db.init_db()
        print("db.init_db() SUCCESS")
    except Exception as e:
        print(f"db.init_db() FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        try:
            if os.path.exists(TEST_DB_PATH):
                 # Try to remove
                 pass 
        except: pass

if __name__ == "__main__":
    test_manual_init()
