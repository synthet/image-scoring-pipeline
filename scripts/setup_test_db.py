import os
import sys
import time

# Firebird-only helper for scoring_history_test.fdb — ignore database.engine in config
# (e.g. when the main app uses PostgreSQL).
os.environ["IMAGE_SCORING_FORCE_FIREBIRD_TEST_SETUP"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules import db

# Tests must only use scoring_history_test.fdb — never production (SCORING_HISTORY.FDB / scoring_history.fdb).
TEST_DB_FILENAME = "scoring_history_test.fdb"

def main():
    test_fdb = os.path.join(db._PROJECT_ROOT, TEST_DB_FILENAME)

    # Force db module to use test DB only (no production DB reference).
    db.DB_FILE = TEST_DB_FILENAME
    db.DB_PATH = test_fdb

    if not os.path.exists(test_fdb):
        print(f"Test DB not found at {test_fdb}. Creating new database and schema...")
        try:
            from firebird.driver import create_database
            create_database(test_fdb, user=db.DB_USER, password=db.DB_PASS)
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
