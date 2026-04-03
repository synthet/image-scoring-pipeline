#!/usr/bin/env python3
"""
Phase 4: Keyword Search Performance Benchmark

Benchmarks keyword search performance:
- Legacy path: IMAGES.KEYWORDS LIKE %keyword%
- Normalized path: IMAGE_KEYWORDS JOIN KEYWORDS_DIM

Target: <150ms for keyword search at 50K+ images
"""

import os
import sys
import logging
import time
import statistics
from typing import List, Tuple

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import db, db_postgres, config
from modules.db_connector import get_connector

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def get_sample_keywords(conn, limit: int = 5) -> List[str]:
    """Get a sample of keywords from the database."""
    try:
        if conn.type == 'postgres':
            rows = conn.query(f"""
                SELECT keyword_norm
                FROM (
                    SELECT DISTINCT kd.keyword_norm
                    FROM keywords_dim kd
                    JOIN image_keywords ik ON kd.keyword_id = ik.keyword_id
                ) subq
                ORDER BY random()
                LIMIT {limit}
            """)
        else:
            rows = conn.query(f"""
                SELECT DISTINCT kd.keyword_norm
                FROM keywords_dim kd
                JOIN image_keywords ik ON kd.keyword_id = ik.keyword_id
                ORDER BY RAND()
                LIMIT {limit}
            """)

        keywords = [row['keyword_norm'] for row in rows]
        logger.info(f"Sample keywords: {keywords}")
        return keywords
    except Exception as e:
        logger.error(f"Failed to get sample keywords: {e}")
        return []


def benchmark_legacy_path(conn, keywords: List[str], num_runs: int = 5) -> dict:
    """Benchmark legacy IMAGES.KEYWORDS LIKE path."""
    logger.info(f"\n=== Legacy Path Benchmark (IMAGES.KEYWORDS LIKE) ===")
    logger.info(f"Testing {len(keywords)} keywords, {num_runs} runs each")

    results = {}

    for keyword in keywords:
        timings = []

        for _ in range(num_runs):
            try:
                start = time.time()

                if conn.type == 'postgres':
                    conn.query("""
                        SELECT COUNT(DISTINCT i.id) AS count
                        FROM images i
                        WHERE i.keywords ILIKE %s
                    """, (f"%{keyword}%",))
                else:
                    conn.query("""
                        SELECT COUNT(DISTINCT i.id) AS count
                        FROM images i
                        WHERE i.keywords LIKE ?
                    """, (f"%{keyword}%",))

                elapsed = (time.time() - start) * 1000  # Convert to ms
                timings.append(elapsed)

            except Exception as e:
                logger.error(f"Legacy search for '{keyword}' failed: {e}")
                timings.append(None)

        valid_timings = [t for t in timings if t is not None]
        if valid_timings:
            results[keyword] = {
                "mean": statistics.mean(valid_timings),
                "median": statistics.median(valid_timings),
                "min": min(valid_timings),
                "max": max(valid_timings),
                "stdev": statistics.stdev(valid_timings) if len(valid_timings) > 1 else 0
            }

    return results


def benchmark_normalized_path(conn, keywords: List[str], num_runs: int = 5) -> dict:
    """Benchmark normalized IMAGE_KEYWORDS JOIN KEYWORDS_DIM path."""
    logger.info(f"\n=== Normalized Path Benchmark (IMAGE_KEYWORDS JOIN) ===")
    logger.info(f"Testing {len(keywords)} keywords, {num_runs} runs each")

    results = {}

    for keyword in keywords:
        timings = []

        for _ in range(num_runs):
            try:
                start = time.time()

                if conn.type == 'postgres':
                    conn.query("""
                        SELECT COUNT(DISTINCT ik.image_id) AS count
                        FROM image_keywords ik
                        JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
                        WHERE kd.keyword_norm ILIKE %s
                    """, (f"%{keyword}%",))
                else:
                    conn.query("""
                        SELECT COUNT(DISTINCT ik.image_id) AS count
                        FROM image_keywords ik
                        JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
                        WHERE kd.keyword_norm LIKE ?
                    """, (f"%{keyword}%",))

                elapsed = (time.time() - start) * 1000  # Convert to ms
                timings.append(elapsed)

            except Exception as e:
                logger.error(f"Normalized search for '{keyword}' failed: {e}")
                timings.append(None)

        valid_timings = [t for t in timings if t is not None]
        if valid_timings:
            results[keyword] = {
                "mean": statistics.mean(valid_timings),
                "median": statistics.median(valid_timings),
                "min": min(valid_timings),
                "max": max(valid_timings),
                "stdev": statistics.stdev(valid_timings) if len(valid_timings) > 1 else 0
            }

    return results


def get_image_count(conn) -> int:
    """Get total image count."""
    try:
        result = conn.query("SELECT COUNT(*) AS count FROM images")
        if result:
            return result[0].get('count', 0)
    except Exception as e:
        logger.error(f"Failed to get image count: {e}")
    return 0


def print_benchmark_results(legacy: dict, normalized: dict):
    """Pretty-print benchmark results."""
    logger.info("\n=== BENCHMARK RESULTS ===\n")
    logger.info(f"{'Keyword':<20} {'Legacy (ms)':<20} {'Normalized (ms)':<20} {'Ratio':<10}")
    logger.info("-" * 70)

    legacy_times = []
    normalized_times = []

    for keyword in legacy.keys():
        if keyword in normalized:
            leg = legacy[keyword]["median"]
            norm = normalized[keyword]["median"]
            ratio = leg / norm if norm > 0 else 0
            logger.info(f"{keyword:<20} {leg:>10.2f}ms       {norm:>10.2f}ms       {ratio:>8.2f}x")

            legacy_times.append(leg)
            normalized_times.append(norm)

    if legacy_times and normalized_times:
        logger.info("-" * 70)
        avg_legacy = statistics.mean(legacy_times)
        avg_norm = statistics.mean(normalized_times)
        avg_ratio = avg_legacy / avg_norm if avg_norm > 0 else 0

        logger.info(f"{'Average':<20} {avg_legacy:>10.2f}ms       {avg_norm:>10.2f}ms       {avg_ratio:>8.2f}x\n")

        # Pass/fail on target
        target_ms = 150
        if avg_norm <= target_ms:
            logger.info(f"✅ PASS: Normalized path averages {avg_norm:.2f}ms (target: <{target_ms}ms)")
        else:
            logger.warning(f"❌ FAIL: Normalized path averages {avg_norm:.2f}ms (target: <{target_ms}ms)")


def main():
    """Run benchmark."""
    engine = config.get_config_value("database.engine", default="postgres")
    logger.info(f"Using database engine: {engine}\n")

    conn = get_connector()

    # Get stats
    image_count = get_image_count(conn)
    logger.info(f"Total images in database: {image_count}\n")

    if image_count == 0:
        logger.warning("No images found in database. Skipping benchmark.")
        return 1

    # Get sample keywords
    keywords = get_sample_keywords(conn, limit=5)
    if not keywords:
        logger.warning("No keywords found in database. Skipping benchmark.")
        return 1

    # Run benchmarks
    legacy_results = benchmark_legacy_path(conn, keywords, num_runs=5)
    normalized_results = benchmark_normalized_path(conn, keywords, num_runs=5)

    # Print results
    print_benchmark_results(legacy_results, normalized_results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
