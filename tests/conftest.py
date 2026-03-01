import sys
import os
import subprocess
import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def pytest_sessionstart(session):
    """
    Called before performing collection and entering the test loop.
    Ensures the test database (scoring_history_test.fdb only — never SCORING_HISTORY.FDB) is ready.
    """
    script_path = os.path.join(project_root, "scripts", "setup_test_db.py")
    print("\n[conftest] Setting up test database (scoring_history_test.fdb only)...")
    
    try:
        # Run setup_test_db.py using a subprocess to recreate SCORING_HISTORY_TEST.FDB
        subprocess.run([sys.executable, script_path], check=True, cwd=project_root)
        print("[conftest] Test database initialized successfully.\n")
    except subprocess.CalledProcessError as e:
        print(f"\n[conftest] WARNING: Test database setup script failed: {e}")
        print("Tests may run against an outdated or locked test DB.")
    except Exception as e:
        print(f"\n[conftest] ERROR: Could not run test database setup: {e}")
