"""
One-time migration script: Firebird SQL → PostgreSQL

Reads all data from an existing Firebird .fdb file and inserts it into
the PostgreSQL database configured in config.json / environment variables.

Prerequisites:
  - firebird-driver must be installed (pip install firebird-driver)
  - PostgreSQL must be running with the musiq database created
  - pgvector extension must be enabled (run: CREATE EXTENSION vector;)
  - The target PostgreSQL schema must already exist (run: python launch.py --init-db-only)

Usage:
  python scripts/python/migrate_firebird_to_postgres.py [options]

Options:
  --fdb-path PATH       Path to the Firebird .fdb file (default: scoring_history.fdb)
  --fdb-user USER       Firebird username (default: sysdba)
  --fdb-password PASS   Firebird password (default: masterkey)
  --batch-size N        Rows per batch (default: 500)
  --skip-table TABLE    Skip a specific table (can be repeated)
  --clear-target        Clear selected target tables before migration
  --dry-run             Print counts without inserting
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Tables to migrate, in dependency order (parents before children)
TABLES_ORDER = [
    "jobs",
    "folders",
    "stacks",
    "images",
    "file_paths",
    "image_exif",
    "image_xmp",
    "cluster_progress",
    "culling_sessions",
    "culling_picks",
    "pipeline_phases",
    "image_phase_status",
]


def get_pg_conn(host, port, dbname, user, password):
    conn = psycopg2.connect(
        host=host, port=port, dbname=dbname, user=user, password=password,
        options="-c client_encoding=UTF8",
    )
    conn.autocommit = False
    register_vector(conn)
    return conn


def get_fb_conn(fdb_path, user, password):
    try:
        from firebird.driver import connect as fb_connect
    except ImportError:
        logger.error("firebird-driver not installed. Run: pip install firebird-driver")
        sys.exit(1)

    return fb_connect(str(fdb_path), user=user, password=password, charset="UTF8")


def get_fb_columns(fb_cur, table_name):
    """Return list of column names for a Firebird table (lowercased)."""
    fb_cur.execute(
        "SELECT RDB$FIELD_NAME FROM RDB$RELATION_FIELDS "
        "WHERE RDB$RELATION_NAME = ? ORDER BY RDB$FIELD_POSITION",
        (table_name.upper(),),
    )
    return [row[0].strip().lower() for row in fb_cur.fetchall()]


def get_pg_columns(pg_cur, table_name):
    """Return list of column names for a PostgreSQL table."""
    pg_cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
        (table_name.lower(),),
    )
    return [row[0] for row in pg_cur.fetchall()]


def table_exists_fb(fb_cur, table_name):
    fb_cur.execute(
        "SELECT 1 FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = ? AND RDB$SYSTEM_FLAG = 0",
        (table_name.upper(),),
    )
    return fb_cur.fetchone() is not None


def table_exists_pg(pg_cur, table_name):
    pg_cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
        (table_name.lower(),),
    )
    return pg_cur.fetchone() is not None


def migrate_table(fb_conn, pg_conn, table_name, batch_size=500, dry_run=False):
    """Migrate a single table from Firebird to PostgreSQL."""
    fb_cur = fb_conn.cursor()
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if not table_exists_fb(fb_cur, table_name):
        logger.info("  Firebird table %s does not exist — skipping", table_name)
        return 0

    if not table_exists_pg(pg_cur, table_name):
        logger.warning("  PostgreSQL table %s does not exist — skipping (run init_db first)", table_name)
        return 0

    # Get column intersection (only migrate columns that exist in both)
    fb_cols = get_fb_columns(fb_cur, table_name)
    pg_cols = get_pg_columns(pg_cur, table_name)
    pg_cols_set = set(pg_cols)

    # Columns to migrate: present in Firebird AND PostgreSQL
    common_cols = [c for c in fb_cols if c in pg_cols_set]
    if not common_cols:
        logger.warning("  No common columns for %s — skipping", table_name)
        return 0

    # Check current PG row count
    pg_cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    existing_count = pg_cur.fetchone()[0]
    if existing_count > 0:
        logger.info("  PostgreSQL %s already has %d rows — skipping (pass --clear-target to clear before migration)", table_name, existing_count)
        return 0

    # Fetch all rows from Firebird
    fb_select_cols = ", ".join(common_cols)
    fb_cur.execute(f"SELECT {fb_select_cols} FROM {table_name}")

    is_embedding_table = table_name == "images"
    embedding_col_idx = common_cols.index("image_embedding") if (is_embedding_table and "image_embedding" in common_cols) else -1

    total_inserted = 0
    batch = []

    def flush_batch(batch):
        if not batch or dry_run:
            return
        placeholders = ", ".join(["%s"] * len(common_cols))
        insert_sql = (
            f"INSERT INTO {table_name} ({', '.join(common_cols)}) "
            f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
        )
        pg_cur.executemany(insert_sql, batch)
        pg_conn.commit()

    while True:
        rows = fb_cur.fetchmany(batch_size)
        if not rows:
            break

        for row in rows:
            converted = list(row)

            # Convert embedding: Firebird BLOB bytes → numpy array for pgvector
            if embedding_col_idx >= 0:
                emb = converted[embedding_col_idx]
                if emb is not None:
                    try:
                        emb_bytes = bytes(emb)
                        converted[embedding_col_idx] = np.frombuffer(emb_bytes, dtype=np.float32)
                    except Exception as e:
                        logger.warning("    Could not convert embedding for row: %s", e)
                        converted[embedding_col_idx] = None

            # Convert Firebird BLOBs to strings for text columns
            for i, val in enumerate(converted):
                if hasattr(val, "read"):
                    try:
                        converted[i] = val.read()
                    except Exception:
                        converted[i] = None

            batch.append(tuple(converted))

        flush_batch(batch)
        total_inserted += len(batch)
        batch = []
        logger.info("  %s: %d rows migrated...", table_name, total_inserted)

    # Flush any remaining
    flush_batch(batch)
    total_inserted += len(batch)

    return total_inserted


def reset_sequences(pg_conn):
    """Reset PostgreSQL SERIAL sequences to MAX(id) + 1 for each table."""
    pg_cur = pg_conn.cursor()
    tables_with_id = [
        "jobs", "folders", "stacks", "images",
        "culling_sessions", "pipeline_phases",
    ]
    for table in tables_with_id:
        try:
            pg_cur.execute(f"SELECT MAX(id) FROM {table}")
            row = pg_cur.fetchone()
            max_id = row[0] if row and row[0] else 0
            pg_cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), %s, true)",
                (max(max_id, 1),),
            )
            logger.info("  Reset sequence for %s to %d", table, max_id)
        except Exception as e:
            logger.warning("  Could not reset sequence for %s: %s", table, e)
    pg_conn.commit()


def clear_target_tables(pg_conn, tables):
    """Clear target tables in reverse dependency order to respect foreign keys."""
    pg_cur = pg_conn.cursor()
    for table in reversed(tables):
        logger.info("Clearing target table: %s", table)
        pg_cur.execute(f"DELETE FROM {table}")
    pg_conn.commit()


def validate_migration(fb_conn, pg_conn, tables):
    """Compare row counts between Firebird and PostgreSQL."""
    fb_cur = fb_conn.cursor()
    pg_cur = pg_conn.cursor()
    logger.info("\nValidation:")
    all_ok = True
    for table in tables:
        if not table_exists_fb(fb_cur, table):
            continue
        fb_cur.execute(f"SELECT COUNT(*) FROM {table}")
        fb_count = fb_cur.fetchone()[0]
        try:
            pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
            pg_count = pg_cur.fetchone()[0]
        except Exception:
            pg_count = "ERROR"

        status = "OK" if fb_count == pg_count else "MISMATCH"
        if status == "MISMATCH":
            all_ok = False
        logger.info("  %-30s FB=%6d  PG=%6s  %s", table, fb_count, pg_count, status)
    return all_ok


def build_parser():
    parser = argparse.ArgumentParser(description="Migrate Firebird DB to PostgreSQL")
    parser.add_argument("--fdb-path", default=None, help="Path to Firebird .fdb file")
    parser.add_argument("--fdb-user", default="sysdba", help="Firebird username")
    parser.add_argument("--fdb-password", default=None, help="Firebird password")
    parser.add_argument("--pg-host", default=None, help="PostgreSQL host")
    parser.add_argument("--pg-port", default=None, type=int, help="PostgreSQL port")
    parser.add_argument("--pg-db", default=None, help="PostgreSQL database name")
    parser.add_argument("--pg-user", default=None, help="PostgreSQL username")
    parser.add_argument("--pg-password", default=None, help="PostgreSQL password")
    parser.add_argument("--batch-size", default=500, type=int, help="Rows per batch")
    parser.add_argument("--skip-table", action="append", default=[], help="Skip a table")
    parser.add_argument(
        "--clear-target",
        action="store_true",
        help="Clear selected target tables before migration",
    )
    parser.add_argument("--dry-run", action="store_true", help="Count rows without inserting")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Resolve paths from project root
    project_root = Path(__file__).parent.parent.parent

    # Load config
    sys.path.insert(0, str(project_root))
    from modules import config as app_config
    db_cfg = app_config.get_config_section("database")

    # Firebird settings
    fdb_path = args.fdb_path or project_root / db_cfg.get("filename", "scoring_history.fdb")
    fdb_user = args.fdb_user
    fdb_password = (
        args.fdb_password
        or os.environ.get("FIREBIRD_PASSWORD")
        or "masterkey"
    )

    # PostgreSQL settings
    pg_host = args.pg_host or os.environ.get("POSTGRES_HOST") or db_cfg.get("host", "localhost")
    pg_port = args.pg_port or int(os.environ.get("POSTGRES_PORT") or db_cfg.get("port", 5432))
    pg_db = args.pg_db or os.environ.get("POSTGRES_DB") or db_cfg.get("dbname", "musiq")
    pg_user = args.pg_user or os.environ.get("POSTGRES_USER") or db_cfg.get("user", "musiq")
    pg_password = (
        args.pg_password
        or os.environ.get("POSTGRES_PASSWORD")
        or db_cfg.get("password", "musiq")
    )

    logger.info("Firebird source: %s (user=%s)", fdb_path, fdb_user)
    logger.info("PostgreSQL target: %s:%d/%s (user=%s)", pg_host, pg_port, pg_db, pg_user)

    if not Path(fdb_path).exists():
        logger.error("Firebird file not found: %s", fdb_path)
        sys.exit(1)

    # Connect
    logger.info("Connecting to Firebird...")
    fb_conn = get_fb_conn(fdb_path, fdb_user, fdb_password)
    logger.info("Connecting to PostgreSQL...")
    pg_conn = get_pg_conn(pg_host, pg_port, pg_db, pg_user, pg_password)

    tables = [t for t in TABLES_ORDER if t not in args.skip_table]

    if args.dry_run:
        logger.info("DRY RUN — no data will be inserted")
        validate_migration(fb_conn, pg_conn, tables)
        return

    if args.clear_target:
        logger.info("--clear-target enabled: clearing target tables before migration")
        clear_target_tables(pg_conn, tables)
    else:
        logger.info("--clear-target not provided: existing target data will be preserved; non-empty tables are skipped")

    # Migrate each table
    total = 0
    for table in tables:
        logger.info("Migrating table: %s", table)
        count = migrate_table(fb_conn, pg_conn, table, args.batch_size, args.dry_run)
        logger.info("  %s: %d rows migrated", table, count)
        total += count

    logger.info("Total rows migrated: %d", total)

    # Reset sequences
    logger.info("Resetting PostgreSQL sequences...")
    reset_sequences(pg_conn)

    # Validate
    all_ok = validate_migration(fb_conn, pg_conn, tables)
    if all_ok:
        logger.info("\nMigration complete — all row counts match!")
    else:
        logger.warning("\nMigration complete with mismatches — review above")

    fb_conn.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
