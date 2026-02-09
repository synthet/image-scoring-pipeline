
import sys
import os
import io
import contextlib

# Add parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock mcp to allow import if not present or to bypass decorators if needed
# But since I want to test the actual logic, I effectively need to call the decorated functions.
# FastMCP tools are usually callable.

try:
    from modules import mcp_server_firebird
    print("Successfully imported mcp_server_firebird")
except ImportError as e:
    print(f"Failed to import: {e}")
    sys.exit(1)

def test_tools():
    print("\n--- Testing list_tables ---")
    try:
        tables = mcp_server_firebird.list_tables()
        print(f"Found {len(tables)} tables")
        if len(tables) > 0:
            print(f"First 5: {tables[:5]}")
    except Exception as e:
        print(f"list_tables failed: {e}")

    print("\n--- Testing get_firebird_version ---")
    try:
        ver = mcp_server_firebird.get_firebird_version()
        print(f"Version: {ver}")
    except Exception as e:
        print(f"get_firebird_version failed: {e}")

    print("\n--- Testing run_sql (SELECT) ---")
    try:
        res = mcp_server_firebird.run_sql("SELECT COUNT(*) FROM images")
        print(f"Result: {res}")
    except Exception as e:
        print(f"run_sql failed: {e}")

if __name__ == "__main__":
    test_tools()
