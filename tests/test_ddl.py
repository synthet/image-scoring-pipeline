import os
import sys
import shutil
import uuid
import pytest

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db
from firebird.driver import connect, driver_config, DatabaseError

DB_DIR = os.path.abspath("temp_ddl_test")
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

DB_PATH = os.path.join(DB_DIR, f"test_ddl_{uuid.uuid4().hex}.fdb")
TEMPLATE_PATH = os.path.abspath("template.fdb")


def test_ddl_simple():
    """Test basic DDL on a Firebird database. Requires template.fdb in project root.
    Create it manually if needed: use Firebird tools or copy an empty .fdb file."""
    if not os.path.exists(TEMPLATE_PATH):
        pytest.skip("template.fdb not found (create empty Firebird DB in project root to run this test)")
    shutil.copy2(TEMPLATE_PATH, DB_PATH)
    print(f"DB: {DB_PATH}")
    
    # Ensure config (db module import should have done it, but let's be unsafe)
    if hasattr(driver_config, 'fb_client_library'):
         fb_dll = os.path.abspath(os.path.join("Firebird", "fbclient.dll"))
         if os.path.exists(fb_dll):
             driver_config.fb_client_library.value = fb_dll
    
    # Connect
    dsn = f"inet://127.0.0.1/{DB_PATH}"
    conn = connect(dsn, user='sysdba', password='masterkey')
    c = conn.cursor()
    
    try:
        # Try simple DDL
        c.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name VARCHAR(50))")
        conn.commit()
        print("Created table successfully")
        
        # Verify
        c.execute("SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = 'TEST_TABLE'")
        assert c.fetchone() is not None
        
    except Exception as e:
        print(f"DDL Failed: {e}")
        raise
    finally:
        conn.close()
        
    # Cleanup
    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    except: pass
