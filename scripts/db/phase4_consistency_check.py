#!/usr/bin/env python3
"""
Phase 4: Keyword Consistency Check

Verifies that IMAGES.KEYWORDS (legacy) matches IMAGE_KEYWORDS/KEYWORDS_DIM (normalized).
Works with both Firebird and Postgres backends.
"""

import os
import sys
import logging
from collections import defaultdict

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import db, db_postgres, config
from modules.db_connector import get_connector

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def check_postgres():
    """Verify keyword consistency on PostgreSQL."""
    logger.info("=== PostgreSQL Keyword Consistency Check ===")

    try:
        with db_postgres.PGConnectionManager() as pg_conn:
            with pg_conn.cursor() as cur:
                # 1. Get all images with legacy keywords
                cur.execute("""
                    SELECT id, file_path, keywords
                    FROM images
                    WHERE keywords IS NOT NULL AND keywords != ''
                """)
                legacy_rows = cur.fetchall()
                logger.info(f"Found {len(legacy_rows)} images with legacy keywords")

                mismatches = []
                missing_normalized = []
                total_checked = 0

                for image_id, file_path, legacy_val in legacy_rows:
                    total_checked += 1

                    # Normalize legacy list
                    legacy_set = {k.strip().lower() for k in legacy_val.split(',') if k.strip()}

                    # Get normalized keywords
                    cur.execute("""
                        SELECT DISTINCT kd.keyword_norm
                        FROM image_keywords ik
                        JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
                        WHERE ik.image_id = %s
                    """, (image_id,))
                    norm_rows = cur.fetchall()
                    norm_set = {r[0] for r in norm_rows}

                    if not norm_set and legacy_set:
                        missing_normalized.append((image_id, file_path))
                    elif legacy_set != norm_set:
                        mismatches.append({
                            "id": image_id,
                            "path": file_path,
                            "legacy": sorted(list(legacy_set)),
                            "normalized": sorted(list(norm_set)),
                            "extra_in_legacy": sorted(list(legacy_set - norm_set)),
                            "extra_in_normalized": sorted(list(norm_set - legacy_set))
                        })

                # 2. Results
                logger.info(f"Checked {total_checked} images.")

                if not mismatches and not missing_normalized:
                    logger.info("✅ SUCCESS: Keyword integrity verified. Legacy and normalized data match perfectly.")
                    return True
                else:
                    if missing_normalized:
                        logger.warning(f"❌ Found {len(missing_normalized)} images missing normalized keyword rows entirely.")
                        for img_id, path in missing_normalized[:10]:
                            logger.debug(f"  Missing: ID {img_id} - {path}")

                    if mismatches:
                        logger.warning(f"❌ Found {len(mismatches)} images with keyword mismatches.")
                        for m in mismatches[:5]:
                            logger.info(f"  ID {m['id']}: {os.path.basename(m['path'])}")
                            logger.info(f"    Legacy: {m['legacy']}")
                            logger.info(f"    Norm:   {m['normalized']}")

                    return False

    except Exception as e:
        logger.error(f"Postgres check failed: {e}", exc_info=True)
        return False


def check_firebird():
    """Verify keyword consistency on Firebird (legacy)."""
    logger.info("=== Firebird Keyword Consistency Check ===")

    try:
        conn = db.get_db()
        c = conn.cursor()

        # 1. Get all images with legacy keywords
        c.execute("SELECT id, file_path, keywords FROM images WHERE keywords IS NOT NULL AND keywords <> ''")
        legacy_rows = c.fetchall()
        logger.info(f"Found {len(legacy_rows)} images with legacy keywords")

        mismatches = []
        missing_normalized = []
        total_checked = 0

        for image_id, file_path, legacy_val in legacy_rows:
            total_checked += 1

            # Normalize legacy list
            legacy_set = {k.strip().lower() for k in legacy_val.split(',') if k.strip()}

            # Get normalized keywords
            c.execute("""
                SELECT kd.keyword_norm
                FROM image_keywords ik
                JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
                WHERE ik.image_id = ?
            """, (image_id,))
            norm_rows = c.fetchall()
            norm_set = {r[0] for r in norm_rows}

            if not norm_set and legacy_set:
                missing_normalized.append((image_id, file_path))
            elif legacy_set != norm_set:
                mismatches.append({
                    "id": image_id,
                    "path": file_path,
                    "legacy": sorted(list(legacy_set)),
                    "normalized": sorted(list(norm_set)),
                    "extra_in_legacy": sorted(list(legacy_set - norm_set)),
                    "extra_in_normalized": sorted(list(norm_set - legacy_set))
                })

        # 2. Results
        logger.info(f"Checked {total_checked} images.")

        if not mismatches and not missing_normalized:
            logger.info("✅ SUCCESS: Keyword integrity verified. Legacy and normalized data match perfectly.")
            return True
        else:
            if missing_normalized:
                logger.warning(f"❌ Found {len(missing_normalized)} images missing normalized keyword rows entirely.")
                for img_id, path in missing_normalized[:10]:
                    logger.debug(f"  Missing: ID {img_id} - {path}")

            if mismatches:
                logger.warning(f"❌ Found {len(mismatches)} images with keyword mismatches.")
                for m in mismatches[:5]:
                    logger.info(f"  ID {m['id']}: {os.path.basename(m['path'])}")
                    logger.info(f"    Legacy: {m['legacy']}")
                    logger.info(f"    Norm:   {m['normalized']}")

            return False

    except Exception as e:
        logger.error(f"Firebird check failed: {e}", exc_info=True)
        return False

    finally:
        conn.close()


def get_table_stats():
    """Get stats on normalized keyword tables."""
    logger.info("\n=== Keyword Table Statistics ===")

    conn = get_connector()

    try:
        if conn.type == 'postgres':
            # Postgres stats
            stats = conn.query("""
                SELECT
                    (SELECT COUNT(*) FROM keywords_dim) AS total_keywords,
                    (SELECT COUNT(*) FROM image_keywords) AS total_keyword_links,
                    (SELECT COUNT(DISTINCT image_id) FROM image_keywords) AS images_with_keywords,
                    (SELECT COUNT(*) FROM images WHERE keywords IS NOT NULL) AS images_with_legacy_keywords
            """)
        else:
            # Firebird stats
            stats = conn.query("""
                SELECT
                    (SELECT COUNT(*) FROM keywords_dim) AS total_keywords,
                    (SELECT COUNT(*) FROM image_keywords) AS total_keyword_links,
                    (SELECT COUNT(DISTINCT image_id) FROM image_keywords) AS images_with_keywords,
                    (SELECT COUNT(*) FROM images WHERE keywords IS NOT NULL) AS images_with_legacy_keywords
            """)

        if stats:
            row = stats[0]
            logger.info(f"  Total keywords in KEYWORDS_DIM: {row.get('total_keywords', 0)}")
            logger.info(f"  Total keyword links: {row.get('total_keyword_links', 0)}")
            logger.info(f"  Images with keywords (normalized): {row.get('images_with_keywords', 0)}")
            logger.info(f"  Images with keywords (legacy): {row.get('images_with_legacy_keywords', 0)}")

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")


def main():
    """Run consistency checks."""
    engine = config.get_config_value("database.engine", default="postgres")
    logger.info(f"Using database engine: {engine}\n")

    if engine == "postgres":
        success = check_postgres()
    else:
        success = check_firebird()

    get_table_stats()

    if success:
        logger.info("\n✅ All consistency checks passed!")
        return 0
    else:
        logger.warning("\n⚠️  Consistency issues found. Consider running db._backfill_keywords()")
        return 1


if __name__ == "__main__":
    sys.exit(main())
