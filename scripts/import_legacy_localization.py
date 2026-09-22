"""Import ``images.bird_bbox`` into the normalized localization tables.

Stage 2 of the early-localization rollout (issue #370). Reads the legacy column and
writes ``image_localization_runs`` / ``image_regions``. Runs **no inference** and writes
nothing back to ``images.bird_bbox``.

Safe to re-run: the insert targets the partial unique index with ``ON CONFLICT DO
NOTHING``, so a second pass skips every image that already has a current run. An
interrupted run resumes from where it stopped, because it pages by ``images.id``.

Usage (see .claude/rules/python-wsl-webapp-env.md for the environment)::

    python scripts/import_legacy_localization.py --dry-run
    python scripts/import_legacy_localization.py --limit 1000
    python scripts/import_legacy_localization.py --yes

``--dry-run`` is the default. Writing requires ``--yes``, because this touches the
production library database.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger("import_legacy_localization")


def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true",
                    help="Actually write. Without this the run is a dry run.")
    ap.add_argument("--dry-run", action="store_true", default=False,
                    help="Explicitly request a dry run (the default when --yes is absent).")
    ap.add_argument("--batch-size", type=int, default=2000,
                    help="Rows per commit (default 2000).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Stop after this many source rows. Useful for a first pass.")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    dry_run = not args.yes
    if args.dry_run and args.yes:
        logger.error("--dry-run and --yes are contradictory; refusing to guess")
        return 2

    import psycopg2

    from modules import db_postgres
    from modules.localization_legacy import import_legacy_bird_bbox

    cfg = db_postgres.get_pg_config()
    logger.info("database: %s@%s:%s/%s", cfg["user"], cfg["host"], cfg["port"], cfg["dbname"])
    logger.info("mode: %s", "DRY RUN (no writes)" if dry_run else "WRITING")

    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"], dbname=cfg["dbname"],
        user=cfg["user"], password=cfg["password"],
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM images WHERE bird_bbox IS NOT NULL")
            source_rows = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM image_localization_runs WHERE is_current")
            already = cur.fetchone()[0]
        logger.info("source rows (bird_bbox IS NOT NULL): %s", f"{source_rows:,}")
        logger.info("existing current runs: %s", f"{already:,}")

        started = time.monotonic()
        counts = import_legacy_bird_bbox(
            conn, batch_size=args.batch_size, dry_run=dry_run, limit=args.limit,
        )
        elapsed = time.monotonic() - started
    finally:
        conn.close()

    logger.info("--- results (%.1fs) ---", elapsed)
    for key in ("scanned", "detected", "no_detection", "retryable_error", "terminal_error",
                "regions", "detected_without_region", "skipped_existing"):
        logger.info("  %-24s %s", key, f"{counts.get(key, 0):,}")

    if counts.get("detected_without_region"):
        logger.warning(
            "%s detected rows had geometry that could not be normalized (inverted, "
            "zero-area, or missing dimensions). Their run rows exist; only the region "
            "was dropped -- deliberately, since clamping would invent a box.",
            f"{counts['detected_without_region']:,}",
        )
    if dry_run:
        logger.info("Dry run: nothing was written. Re-run with --yes to import.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
