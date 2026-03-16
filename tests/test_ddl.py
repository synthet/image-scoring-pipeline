import os
import sys
import shutil
import uuid
import subprocess
import pytest

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db
from firebird.driver import connect, DatabaseError

DB_DIR = os.path.abspath("temp_ddl_test")
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

DB_PATH = os.path.join(DB_DIR, f"test_ddl_{uuid.uuid4().hex}.fdb")
TEMPLATE_PATH = os.path.abspath("template.fdb")


def _resolve_firebird_host():
    """Resolve Firebird server host (same logic as db.get_db for WSL)."""
    host = os.environ.get("FIREBIRD_HOST")
    if host:
        return host
    if os.name == "nt":
        return "127.0.0.1"
    try:
        out = subprocess.check_output(["ip", "route", "show", "default"], timeout=2).decode().strip()
        if "via" in out:
            return out.split("via")[1].split()[0]
    except Exception:
        pass
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                if "nameserver" in line:
                    return line.split()[1]
    except (OSError, IndexError):
        pass
    return "127.0.0.1"


def test_ddl_simple():
    """Test basic DDL on a Firebird database. Requires template.fdb in project root.
    Create it manually if needed: use Firebird tools or copy an empty .fdb file.
    Requires Firebird server running (e.g. via scripts/start_db.ps1)."""
    if not os.path.exists(TEMPLATE_PATH):
        pytest.skip("template.fdb not found (create empty Firebird DB in project root to run this test)")
    shutil.copy2(TEMPLATE_PATH, DB_PATH)
    print(f"DB: {DB_PATH}")

    # Use Windows path when on WSL so the Firebird server (on Windows) can find the file
    db_path_for_dsn = db._to_win_path(DB_PATH) if db._is_wsl() else DB_PATH
    host = _resolve_firebird_host()
    dsn = f"inet://{host}/{db_path_for_dsn}"

    try:
        conn = connect(dsn, user='sysdba', password='masterkey')
    except DatabaseError as e:
        if "Failed to establish a connection" in str(e) or "Unable to complete network request" in str(e):
            pytest.skip(f"Firebird server not reachable at {host}:3050 (start it via scripts/start_db.ps1)")
        raise
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
