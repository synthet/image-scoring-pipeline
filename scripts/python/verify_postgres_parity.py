"""
Verify row-count parity between Firebird and PostgreSQL.

Run after enabling dual_write and letting the app process some data,
or after running migrate_firebird_to_postgres.py.

Usage:
  python scripts/python/verify_postgres_parity.py [--fdb-path PATH] [--threshold N]

Options:
  --fdb-path PATH     Path to .fdb file (default: from config.json)
  --fdb-user USER     Firebird username (default: sysdba)
  --fdb-password PASS Firebird password (default: masterkey)
  --threshold N       Max allowed row-count difference (default: 0 for exact match)
  --table TABLE       Check only this table (can be repeated)
  --quiet             Only print tables with mismatches
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Allow running from repo root or scripts/python/
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules import config
from modules import db_postgres

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TABLES = [
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
]


def get_fb_conn(fdb_path: str, user: str, password: str):
    try:
        from firebird.driver import connect, driver_config
    except ImportError:
        logger.error("firebird-driver not installed. Run: pip install firebird-driver")
        sys.exit(1)

    db_cfg = config.get_config_section("database")
    host = db_cfg.get("host", "localhost")
    port = db_cfg.get("port", 3050)

    conn_str = f"{host}/{port}:{fdb_path}"
    logger.info("Connecting to Firebird: %s", conn_str)
    return connect(conn_str, user=user, password=password)


def count_firebird(fb_conn, table: str) -> int:
    with fb_conn.cursor() as cur:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            row = cur.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.warning("Firebird count failed for %s: %s", table, e)
            return -1


def count_postgres(pg_conn, table: str) -> int:
    with pg_conn.cursor() as cur:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            row = cur.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.warning("PostgreSQL count failed for %s: %s", table, e)
            return -1


def main():
    parser = argparse.ArgumentParser(description="Verify Firebird ↔ PostgreSQL row-count parity")
    parser.add_argument("--fdb-path", default=None)
    parser.add_argument("--fdb-user", default="sysdba")
    parser.add_argument("--fdb-password", default=None)
    parser.add_argument("--threshold", type=int, default=0,
                        help="Max allowed row difference (0 = exact match required)")
    parser.add_argument("--table", action="append", dest="tables",
                        help="Check only this table (repeatable)")
    parser.add_argument("--quiet", action="store_true",
                        help="Only print tables with mismatches")
    args = parser.parse_args()

    db_cfg = config.get_config_section("database")

    fdb_path = args.fdb_path or db_cfg.get("filename", "scoring_history.fdb")
    if not Path(fdb_path).is_absolute():
        fdb_path = str(Path(__file__).resolve().parents[2] / fdb_path)

    fdb_user = args.fdb_user
    fdb_password = args.fdb_password or os.environ.get("FIREBIRD_PASSWORD") or db_cfg.get("password", "masterkey")

    tables_to_check = args.tables or TABLES

    # Connect
    fb_conn = get_fb_conn(fdb_path, fdb_user, fdb_password)
    try:
        with db_postgres.PGConnectionManager() as pg_conn:
            _run_checks(fb_conn, pg_conn, tables_to_check, args.threshold, args.quiet)
    finally:
        fb_conn.close()


def _run_checks(fb_conn, pg_conn, tables: list, threshold: int, quiet: bool):
    col_w = max(len(t) for t in tables) + 2
    header = f"{'Table':<{col_w}}  {'Firebird':>10}  {'PostgreSQL':>10}  {'Diff':>8}  Status"
    sep = "-" * len(header)

    print(header)
    print(sep)

    mismatches = []
    errors = []

    for table in tables:
        fb_count = count_firebird(fb_conn, table)
        pg_count = count_postgres(pg_conn, table)

        if fb_count == -1 or pg_count == -1:
            status = "ERROR"
            errors.append(table)
        else:
            diff = abs(fb_count - pg_count)
            ok = diff <= threshold
            status = "OK" if ok else f"MISMATCH ({diff:+d})"
            if not ok:
                mismatches.append((table, fb_count, pg_count, diff))

        if not quiet or status != "OK":
            diff_str = "" if fb_count == -1 or pg_count == -1 else str(pg_count - fb_count)
            print(f"{table:<{col_w}}  {fb_count:>10}  {pg_count:>10}  {diff_str:>8}  {status}")

    print(sep)

    if mismatches:
        print(f"\n{len(mismatches)} table(s) with row-count mismatch:")
        for t, fb, pg, d in mismatches:
            print(f"  {t}: Firebird={fb}, PostgreSQL={pg}, diff={d}")
        sys.exit(1)
    elif errors:
        print(f"\n{len(errors)} table(s) had errors (check logs above).")
        sys.exit(2)
    else:
        print(f"\nAll {len(tables)} tables match (threshold={threshold}). Parity verified.")


if __name__ == "__main__":
    main()
