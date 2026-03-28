import sys
import os
import re
import glob
import subprocess
import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

POSTGRES_TEST_DB = "image_scoring_test"


def _postgres_tests_enabled(config):
    if os.environ.get("RUN_POSTGRES_TESTS", "").strip().lower() in ("1", "true", "yes"):
        return True
    markexpr = (getattr(config.option, "markexpr", None) or "").strip()
    if not markexpr:
        return False
    return bool(re.search(r"\bpostgres\b", markexpr, re.IGNORECASE))


@pytest.fixture(scope="session")
def postgres_test_session(request):
    """
    Isolated PostgreSQL database (image_scoring_test) with full app schema.
    Opt-in: set RUN_POSTGRES_TESTS=1 or run ``pytest -m postgres``.
    """
    if not _postgres_tests_enabled(request.config):
        pytest.skip(
            "PostgreSQL tests disabled; set RUN_POSTGRES_TESTS=1 or run pytest -m postgres"
        )

    try:
        from modules import db_postgres
    except ModuleNotFoundError as e:
        pytest.skip(f"PostgreSQL driver not available: {e}")

    prev_db = os.environ.get("POSTGRES_DB")
    os.environ["POSTGRES_DB"] = POSTGRES_TEST_DB
    db_postgres.reset_pool()
    try:
        try:
            db_postgres.ensure_database_exists(POSTGRES_TEST_DB)
        except Exception as e:
            pytest.skip(f"PostgreSQL unavailable (create DB): {e}")
        db_postgres.reset_pool()
        try:
            db_postgres.init_db()
        except Exception as e:
            pytest.skip(f"PostgreSQL schema init failed: {e}")
        yield POSTGRES_TEST_DB
    finally:
        db_postgres.reset_pool()
        if prev_db is None:
            os.environ.pop("POSTGRES_DB", None)
        else:
            os.environ["POSTGRES_DB"] = prev_db


@pytest.fixture
def clean_postgres(postgres_test_session):
    """Empty all app tables before each test (requires postgres_test_session)."""
    from modules import db_postgres

    db_postgres.truncate_app_tables()
    yield

def pytest_sessionstart(session):
    """
    Called before performing collection and entering the test loop.
    Ensures the test database (scoring_history_test.fdb only — never SCORING_HISTORY.FDB) is ready.
    """
    if os.environ.get("SKIP_TEST_DB_SETUP", "").strip().lower() in ("1", "true", "yes"):
        print("\n[conftest] SKIP_TEST_DB_SETUP set — skipping scripts/setup_test_db.py (CI / no Firebird).\n")
        return
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


def pytest_sessionfinish(session, exitstatus):
    """Best-effort removal of orphan Firebird test DBs and migration *.bak sidecars at repo root."""
    patterns = (
        os.path.join(project_root, "TEST_*.fdb"),
        os.path.join(project_root, "TEST_*.fdb.*"),
    )
    for pattern in patterns:
        for path in glob.glob(pattern):
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
