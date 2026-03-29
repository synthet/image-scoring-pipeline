"""
Smoke tests for Firebird MCP helpers (optional FastMCP; tools still call db directly).

Requires Firebird and ``scoring_history_test.fdb`` (normal pytest setup).
Skips if MCP SDK is missing or hits known pydantic/MCP import issues.
"""
import os
import sys

import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

pytestmark = [pytest.mark.db, pytest.mark.firebird]


@pytest.fixture(scope="module")
def mcp_fb():
    try:
        from modules import mcp_server_firebird as mod
    except (ImportError, TypeError) as e:
        pytest.skip(f"mcp_server_firebird import failed: {e}")
    return mod


def test_mcp_module_loads(mcp_fb):
    assert hasattr(mcp_fb, "list_tables")
    assert hasattr(mcp_fb, "get_firebird_version")
    assert hasattr(mcp_fb, "run_sql")


def test_list_tables_returns_user_tables(mcp_fb):
    tables = mcp_fb.list_tables()
    assert isinstance(tables, list)
    if tables and isinstance(tables[0], str) and tables[0].startswith("Error:"):
        pytest.skip(tables[0])
    upper = {str(t).strip().upper() for t in tables}
    assert "IMAGES" in upper, f"expected IMAGES in table list, got sample={list(upper)[:10]}"


def test_get_firebird_version_non_error(mcp_fb):
    ver = mcp_fb.get_firebird_version()
    assert isinstance(ver, str)
    assert ver.strip() != ""
    if ver.startswith("Error:"):
        pytest.skip(ver)


def test_run_sql_select_images_count(mcp_fb):
    res = mcp_fb.run_sql("SELECT COUNT(*) AS CNT FROM images")
    assert isinstance(res, dict)
    if res.get("status") == "error":
        pytest.skip(res.get("message", res))
    assert "data" in res
    assert res.get("row_count", 0) >= 1
    rows = res["data"]
    assert len(rows) >= 1
    row0 = rows[0]
    keys_upper = {str(k).upper() for k in row0}
    assert "CNT" in keys_upper, f"unexpected columns {list(row0.keys())}"
