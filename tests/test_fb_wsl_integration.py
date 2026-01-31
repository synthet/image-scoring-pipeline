"""
WSL-only Firebird DB integration smoke test.

This validates that `modules.db.get_db()` can connect and execute a simple query.
Skips on Windows.
"""

import os
import sys
import pytest

pytestmark = [pytest.mark.wsl, pytest.mark.firebird]

if sys.platform.startswith("win"):
    pytest.skip("WSL-only (Firebird integration smoke test)", allow_module_level=True)

# Ensure repo root is on path (when invoked from tests/).
sys.path.insert(0, os.getcwd())


def test_firebird_db_connection_smoke():
    from modules import db

    conn = db.get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM images")
        row = cur.fetchone()
        assert row is not None
        assert isinstance(row[0], int)
    finally:
        conn.close()
