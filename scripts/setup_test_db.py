import os
import shutil
import subprocess
import sys
import time

# Firebird-only helper for scoring_history_test.fdb — ignore database.engine in config
# (e.g. when the main app uses PostgreSQL).
os.environ["IMAGE_SCORING_FORCE_FIREBIRD_TEST_SETUP"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules import db

# Tests must only use scoring_history_test.fdb — never production (SCORING_HISTORY.FDB / scoring_history.fdb).
TEST_DB_FILENAME = "scoring_history_test.fdb"


def _firebird_tool_dir() -> str:
    """Directory containing fbclient.dll / isql (repo-bundled Windows kit)."""
    return os.path.normpath(os.path.join(db._PROJECT_ROOT, "Firebird"))


def _isql_exe() -> str:
    env = os.environ.get("FIREBIRD_ISQL")
    if env and os.path.isfile(env):
        return env
    bundled = os.path.join(_firebird_tool_dir(), "isql.exe")
    if os.path.isfile(bundled):
        return bundled
    for name in ("isql.exe", "isql"):
        w = shutil.which(name)
        if w:
            return w
    raise FileNotFoundError(
        "isql not found (bundled Firebird/, PATH, or FIREBIRD_ISQL). Install Firebird client tools."
    )


def _create_empty_database_fdb(path: str) -> None:
    """Create a new empty .fdb using isql (firebird-driver create_database() breaks on bare paths)."""
    isql = _isql_exe()
    fb_dir = _firebird_tool_dir()
    if not os.path.isdir(fb_dir):
        fb_dir = os.path.dirname(isql) or os.getcwd()
    # Firebird on Windows expects forward slashes in CREATE DATABASE path
    db_sql_path = path.replace("\\", "/")
    cmd = f"CREATE DATABASE '{db_sql_path}' user '{db.DB_USER}' password '{db.DB_PASS}'; EXIT;\n"
    env = os.environ.copy()
    env["FIREBIRD"] = fb_dir
    if fb_dir not in env.get("PATH", ""):
        env["PATH"] = env.get("PATH", "") + os.pathsep + fb_dir
    res = subprocess.run(
        [isql, "-q"],
        input=cmd.encode("utf-8", errors="replace"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=fb_dir,
    )
    if res.returncode != 0:
        err = res.stderr.decode(errors="replace").strip() or res.stdout.decode(errors="replace").strip()
        raise RuntimeError(f"isql CREATE DATABASE failed (exit {res.returncode}): {err}")


def main():
    test_fdb = os.path.join(db._PROJECT_ROOT, TEST_DB_FILENAME)

    # Force db module to use test DB only (no production DB reference).
    db.DB_FILE = TEST_DB_FILENAME
    db.DB_PATH = test_fdb

    if not os.path.exists(test_fdb):
        print(f"Test DB not found at {test_fdb}. Creating new database and schema...")
        try:
            _create_empty_database_fdb(test_fdb)
            time.sleep(0.5)
        except Exception as e:
            print(f"Failed to create test DB: {e}")
            sys.exit(1)
        db.init_db()
        print("Test DB created and initialized.")
        return

    print("Wiping existing test DB data...")
    try:
        conn = db.get_db()
        c = conn.cursor()

        # Clear tables in order of foreign key constraints (roughly)
        tables = ["culling_picks", "culling_sessions", "file_paths", "images", "stacks", "folders"]
        for table in tables:
            try:
                print(f"Clearing {table}...")
                c.execute(f"DELETE FROM {table}")
                conn.commit()
            except Exception as e:
                print(f"Failed to clear {table} (it might be empty or not exist): {e}")

        conn.close()
        print("Test DB setup complete.")
    except Exception as e:
        print(f"Failed to connect or clear test DB: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
