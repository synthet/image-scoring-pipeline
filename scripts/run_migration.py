#!/usr/bin/env python
"""
Standalone Phase 1 Database Migration Runner.

Runs the Phase 1 integrity + index hardening migration independently
of the WebUI or scoring pipeline. Use this when:
  - The WebUI startup hangs due to Electron holding DB locks
  - You want to run migrations on a schedule or in CI
  - You need to test the migration against a copy of the DB

Usage:
    python scripts/run_migration.py                # Default DB path from config
    python scripts/run_migration.py --db-path /path/to/scoring_history.FDB

Requirements:
    - Close the Electron app BEFORE running this script
    - Firebird server must be running
"""
import os
import sys
import time
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    parser = argparse.ArgumentParser(description="Run Phase 1 DB migration independently")
    parser.add_argument("--db-path", help="Override DB path (default: from config)")
    parser.add_argument("--skip-backup", action="store_true", help="Skip automatic backup")
    args = parser.parse_args()

    # Override DB path if provided
    if args.db_path:
        os.environ.setdefault("DB_PATH", args.db_path)

    print("=" * 60)
    print("  Phase 1: DB Schema Migration Runner")
    print("=" * 60)
    print()

    # Import after path setup
    from modules import db

    if args.db_path:
        db.DB_PATH = args.db_path

    print(f"DB Path: {db.DB_PATH}")
    print()

    # Test connection first
    print("[1/3] Testing database connection...")
    try:
        conn = db.get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM images")
        count = c.fetchone()[0]
        print(f"  [OK] Connected. Images table has {count} rows.")
        conn.close()
    except Exception as e:
        print(f"  [FAIL] Connection failed: {e}")
        print()
        print("Make sure:")
        print("  - Firebird server is running")
        print("  - The Electron app is closed")
        print("  - The DB path is correct")
        sys.exit(1)

    # Backup
    if not args.skip_backup:
        print("[2/3] Creating backup...")
        try:
            db._backup_db()
            print("  [OK] Backup created.")
        except Exception as e:
            print(f"  [WARN] Backup failed: {e} (continuing anyway)")
    else:
        print("[2/3] Skipping backup (--skip-backup)")

    # Run migration
    print("[3/3] Running migration...")
    print()
    start = time.time()

    try:
        # Reset the init flag so init_db() actually runs
        db._db_initialized = False
        db.init_db()
        elapsed = time.time() - start
        print()
        print(f"  [OK] Migration completed in {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - start
        print()
        print(f"  [FAIL] Migration failed after {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Quick verification
    print()
    print("=" * 60)
    print("  Post-migration verification")
    print("=" * 60)
    print()

    try:
        conn = db.get_db()
        c = conn.cursor()

        # Check orphans
        c.execute("SELECT COUNT(*) FROM stacks WHERE best_image_id IS NOT NULL AND best_image_id NOT IN (SELECT id FROM images)")
        orphans = c.fetchone()[0]
        status = "[OK]" if orphans == 0 else "[FAIL]"
        print(f"  {status} Orphan STACKS.BEST_IMAGE_ID: {orphans}")

        # Check new indexes
        for idx in ('UQ_IMAGES_FILE_PATH', 'IDX_IMAGES_FOLDER_SCORE', 'IDX_IMAGES_STACK_SCORE', 'UQ_FOLDERS_PATH'):
            exists = db._index_exists(c, idx)
            status = "[OK]" if exists else "[FAIL]"
            print(f"  {status} Index {idx}: {'exists' if exists else 'MISSING'}")

        # Check new FKs
        for fk in ('FK_STACKS_BEST_IMAGE', 'FK_IMAGES_JOB', 'FK_IMAGES_STACK', 'FK_IPS_JOB'):
            exists = db._constraint_exists(c, fk)
            status = "[OK]" if exists else "[FAIL]"
            print(f"  {status} FK {fk}: {'exists' if exists else 'MISSING'}")

        # Check CHECKs
        for chk in ('CHK_IMAGES_LABEL', 'CHK_IMAGES_CULL_DECISION', 'CHK_IPS_STATUS'):
            exists = db._constraint_exists(c, chk)
            status = "[OK]" if exists else "[FAIL]"
            print(f"  {status} CHECK {chk}: {'exists' if exists else 'MISSING'}")

        # Check legacy artifacts removed
        c.execute("""
            SELECT COUNT(*) FROM rdb$relation_constraints
            WHERE rdb$relation_name = 'CULLING_PICKS'
              AND rdb$constraint_type = 'FOREIGN KEY'
              AND rdb$constraint_name NOT STARTING WITH 'FK_'
        """)
        legacy = c.fetchone()[0]
        status = "[OK]" if legacy == 0 else "[FAIL]"
        print(f"  {status} Legacy CULLING_PICKS FK artifacts: {legacy}")

        conn.close()
    except Exception as e:
        print(f"  [WARN] Verification query failed: {e}")

    print()
    print("Done.")

if __name__ == "__main__":
    main()
