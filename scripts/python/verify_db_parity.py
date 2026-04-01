"""
Database Parity Verification: Firebird SQL vs PostgreSQL

This script compares an existing Firebird database against the migrated
PostgreSQL database to ensure data integrity.

Checks:
1. Row count parity for all tables.
2. Content parity for random samples (spot checks).
3. Embedding parity (numpy array comparison for pgvector).

Usage:
  python scripts/python/verify_db_parity.py [options]
"""

import argparse
import logging
import os
import sys
import random
import datetime
from pathlib import Path

import numpy as np
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Tables to verify, in dependency order
TABLES_ORDER = [
    "jobs",
    "folders",
    "stacks",
    "images",
    "file_paths",
    "job_phases",
    "job_steps",
    "image_exif",
    "image_xmp",
    "cluster_progress",
    "culling_sessions",
    "culling_picks",
    "pipeline_phases",
    "image_phase_status",
    "stack_cache",
    "keywords_dim",
    "image_keywords",
]

def get_pg_conn(host, port, dbname, user, password):
    conn = psycopg2.connect(
        host=host, port=port, dbname=dbname, user=user, password=password,
        options="-c client_encoding=UTF8",
    )
    conn.autocommit = True
    register_vector(conn)
    return conn

def get_fb_conn(fdb_path, user, password):
    try:
        from firebird.driver import connect as fb_connect
        from firebird.driver import driver_config
    except ImportError:
        logger.error("firebird-driver not installed. Run: pip install firebird-driver")
        sys.exit(1)

    if os.name == "nt":
        project_root = Path(__file__).resolve().parent.parent.parent
        fb_dll = project_root / "Firebird" / "fbclient.dll"
        if fb_dll.exists():
            driver_config.fb_client_library.value = str(fb_dll)

    return fb_connect(str(fdb_path), user=user, password=password, charset="UTF8")

def get_fb_columns(fb_cur, table_name):
    fb_cur.execute(
        "SELECT RDB$FIELD_NAME FROM RDB$RELATION_FIELDS "
        "WHERE RDB$RELATION_NAME = ? ORDER BY RDB$FIELD_POSITION",
        (table_name.upper(),),
    )
    return [row[0].strip().lower() for row in fb_cur.fetchall()]

def get_pg_columns(pg_cur, table_name):
    pg_cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
        (table_name.lower(),),
    )
    return [row[0] for row in pg_cur.fetchall()]

def compare_values(v1, v2, col_name):
    """Fuzzy comparison of values across dialects."""
    if v1 is None and v2 is None:
        return True
    if v1 is None or v2 is None:
        return False

    # Handle embeddings
    if col_name == "image_embedding":
        try:
            arr1 = np.frombuffer(bytes(v1), dtype=np.float32)
            arr2 = np.array(v2)
            return np.allclose(arr1, arr2, atol=1e-5)
        except Exception:
            return False

    # Handle datetimes
    if isinstance(v1, datetime.datetime) and isinstance(v2, datetime.datetime):
        # Firebird vs Postgres precision differences
        return abs((v1 - v2).total_seconds()) < 1.0

    # Handle Blobs / Bytes
    if hasattr(v1, "read"): # FB Blob
        v1 = v1.read()
    if isinstance(v1, bytes) and isinstance(v2, (bytes, memoryview)):
        return bytes(v1) == bytes(v2)

    # Handle Booleans (FB 0/1 vs PG bool or 0/1)
    if isinstance(v1, bool) and not isinstance(v2, bool):
        return (1 if v1 else 0) == v2
    if not isinstance(v1, bool) and isinstance(v2, bool):
        return v1 == (1 if v2 else 0)

    # Standard comparison
    if str(v1).strip() == str(v2).strip():
        return True

    return v1 == v2

def verify_parity(fb_conn, pg_conn, samples=10):
    fb_cur = fb_conn.cursor()
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    all_passed = True

    try:
        for table in TABLES_ORDER:
            logger.info("-" * 40)
            logger.info("Checking table: %s", table)

            # 1. Count check
            fb_cur.execute(f"SELECT COUNT(*) FROM {table}")
            f_count = fb_cur.fetchone()[0]
            pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
            p_count = pg_cur.fetchone()[0]

            if f_count != p_count:
                logger.error("  [FAIL] Count Mismatch: FB=%d, PG=%d", f_count, p_count)
                all_passed = False
            else:
                logger.info("  [OK] Counts match: %d", f_count)

            if f_count == 0:
                continue

            # 2. Sample data check
            # Find common columns
            fb_cols = get_fb_columns(fb_cur, table)
            pg_cols = get_pg_columns(pg_cur, table)
            common = [c for c in fb_cols if c in pg_cols]

            # Try to find a primary key or ID for sampling
            pk_col = "id" if "id" in common else (common[0] if common else None)
            if not pk_col:
                logger.warning("  [SKIP] No suitable PK for sampling")
                continue

            # Get random IDs from PG (easier to sample)
            pg_cur.execute(f"SELECT {pk_col} FROM {table} ORDER BY RANDOM() LIMIT %s", (samples,))
            sample_ids = [r[0] for r in pg_cur.fetchall()]

            table_passed = True
            for sid in sample_ids:
                # Fetch from FB
                fb_cur.execute(f"SELECT {', '.join(common)} FROM {table} WHERE {pk_col} = ?", (sid,))
                f_row_raw = fb_cur.fetchone()
                if not f_row_raw:
                    logger.error("  [FAIL] ID %s missing in Firebird", sid)
                    table_passed = False
                    continue

                f_row = dict(zip(common, f_row_raw))

                # Fetch from PG
                pg_cur.execute(f"SELECT {', '.join(common)} FROM {table} WHERE {pk_col} = %s", (sid,))
                p_row = pg_cur.fetchone()

                for col in common:
                    if not compare_values(f_row[col], p_row[col], col):
                        logger.error("  [FAIL] Content mismatch at ID %s, Col %s", sid, col)
                        logger.debug("    FB: %s", f_row[col])
                        logger.debug("    PG: %s", p_row[col])
                        table_passed = False

            if table_passed:
                logger.info("  [OK] %d samples verified", len(sample_ids))
            else:
                all_passed = False

    finally:
        fb_cur.close()
        pg_cur.close()

    return all_passed

def main():
    parser = argparse.ArgumentParser(description="Verify database parity between Firebird and PostgreSQL")
    parser.add_argument("--fdb-path", help="Path to Firebird .fdb file")
    parser.add_argument("--samples", type=int, default=10, help="Number of rows to sample per table")
    parser.add_argument("--pg-host", default="localhost")
    parser.add_argument("--pg-port", default=5432, type=int)
    parser.add_argument("--pg-db", default="image_scoring")
    parser.add_argument("--pg-user", default="postgres")
    parser.add_argument("--pg-password", default="postgres")
    args = parser.parse_args()

    # Load app config for defaults if needed
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    try:
        from modules import config as app_config
        db_cfg = app_config.get_config_section("database")
        fdb_path = args.fdb_path or project_root / db_cfg.get("filename", "scoring_history.fdb")
        p_cfg = db_cfg.get("postgres", {})
        pg_host = args.pg_host or p_cfg.get("host", "localhost")
        pg_port = args.pg_port or p_cfg.get("port", 5432)
        pg_db = args.pg_db or p_cfg.get("dbname", "image_scoring")
        pg_user = args.pg_user or p_cfg.get("user", "postgres")
        pg_password = args.pg_password or p_cfg.get("password", "postgres")
    except Exception:
        fdb_path = args.fdb_path or "scoring_history.fdb"
        pg_host, pg_port, pg_db, pg_user, pg_password = args.pg_host, args.pg_port, args.pg_db, args.pg_user, args.pg_password

    logger.info("Firebird Source: %s", fdb_path)
    logger.info("PostgreSQL Target: %s:%s/%s", pg_host, pg_port, pg_db)

    if not Path(fdb_path).exists():
        logger.error("Firebird file not found: %s", fdb_path)
        sys.exit(1)

    fb_conn = get_fb_conn(fdb_path, "sysdba", "masterkey")
    pg_conn = get_pg_conn(pg_host, pg_port, pg_db, pg_user, pg_password)

    try:
        success = verify_parity(fb_conn, pg_conn, samples=args.samples)
        if success:
            logger.info("\nSUCCESS: All integrity checks passed.")
            sys.exit(0)
        else:
            logger.error("\nFAILURE: Mismatches detected across databases.")
            sys.exit(1)
    finally:
        fb_conn.close()
        pg_conn.close()

if __name__ == "__main__":
    main()
