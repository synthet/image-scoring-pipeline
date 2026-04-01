#!/usr/bin/env python3
"""
Populate missing image embeddings in the database.

Finds images with NULL image_embedding, computes MobileNetV2 embeddings via
ClusteringEngine, and writes them to the DB. Used by similar search, tag
propagation, and diversity/MMR.

Execution:
  - WSL: source ~/.venvs/tf and run this file from the repo root (see project rules).
  - Windows: canonical launcher is scripts/maintenance/run_populate_embeddings.bat
    (passes args through). Legacy alias: run_populate_missing_embeddings.bat.

See docs/technical/EMBEDDINGS.md for model semantics, schema notes, and multi-vector guidance.
"""
# Suppress TF logging before any TF import
import os as _os
_os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import sys
import os
import argparse
import logging
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules import db, utils, config
from modules.thumbnails import get_thumb_wsl

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _resolve_wsl_path(row):
    """
    Resolve a WSL-accessible path for an image row.
    Uses get_thumb_wsl(row) if available and exists, else convert_path_to_wsl(file_path).
    """
    thumb = get_thumb_wsl(row)
    if thumb and os.path.exists(thumb):
        return thumb
    try:
        fp = row["file_path"] if "file_path" in row.keys() else row[1]
    except (KeyError, IndexError, TypeError):
        return None
    if not fp:
        return None
    # Convert Windows path to WSL if needed
    wsl_path = utils.convert_path_to_wsl(fp) if hasattr(utils, "convert_path_to_wsl") else fp
    return wsl_path if os.path.exists(wsl_path) else None


def main():
    parser = argparse.ArgumentParser(
        description="Populate missing image embeddings in the database (run in WSL with ~/.venvs/tf)"
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=None,
        help="Restrict to images in this folder path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of images to process",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Override clustering batch size (default from config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report count and paths only, do not write to DB",
    )
    parser.add_argument(
        "--resume-after-id",
        type=int,
        default=None,
        metavar="ID",
        help="Only include rows with id > ID (stable resume after interruption; ordered by id)",
    )
    args = parser.parse_args()

    db.init_db()

    from modules.clustering import CLUSTER_VERSION
    from modules.similar_search import EMBEDDING_DIM

    logger.info(
        "Embedding backfill: MobileNetV2 (ImageNet GAP), dim=%s, CLUSTER_VERSION=%s",
        EMBEDDING_DIM,
        CLUSTER_VERSION,
    )

    rows = db.get_images_missing_embeddings(
        folder_path=args.folder,
        limit=args.limit,
        min_id_exclusive=args.resume_after_id,
    )
    total = len(rows)
    logger.info("Found %d images with missing embeddings.", total)

    if total == 0:
        logger.info("Nothing to do.")
        return 0

    if args.dry_run:
        for i, row in enumerate(rows[:10]):
            path = _resolve_wsl_path(row)
            img_id = row["id"] if "id" in row.keys() else row[0]
            exists = path and os.path.exists(path)
            logger.info("  [%d] id=%s path=%s exists=%s", i + 1, img_id, path, exists)
        if total > 10:
            logger.info("  ... and %d more", total - 10)
        logger.info("Dry run complete. Would process %d images.", total)
        return 0

    batch_size = args.batch_size
    if batch_size is None:
        processing_config = config.get_config_section("processing")
        batch_size = processing_config.get("clustering_batch_size", 32)

    from modules.clustering import ClusteringEngine

    engine = ClusteringEngine()
    updated_count = 0
    skipped_count = 0
    error_count = 0

    # Build list of (image_id, resolved_path) for images we can access
    to_process = []
    for row in rows:
        path = _resolve_wsl_path(row)
        img_id = row["id"] if "id" in row.keys() else row[0]
        if path and os.path.exists(path):
            to_process.append((img_id, path))
        else:
            skipped_count += 1
            fp = row["file_path"] if "file_path" in row.keys() else row[1]
            logger.warning("Skipping id=%s (path not found): %s", img_id, fp)

    # Process in batches
    for i in range(0, len(to_process), batch_size):
        batch = to_process[i : i + batch_size]
        batch_ids = [p[0] for p in batch]
        batch_paths = [p[1] for p in batch]

        try:
            features, valid_indices = engine.extract_features(batch_paths)
        except Exception as e:
            logger.error("Error extracting features for batch: %s", e)
            error_count += len(batch)
            continue

        if not features.size:
            continue

        embedding_pairs = []
        for j, orig_idx in enumerate(valid_indices):
            img_id = batch_ids[orig_idx]
            vec = features[j].astype("float32")
            embedding_pairs.append((img_id, vec.tobytes()))

        if embedding_pairs:
            try:
                db.update_image_embeddings_batch(embedding_pairs)
                updated_count += len(embedding_pairs)
                logger.info("Progress: %d/%d images updated", min(i + len(batch), len(to_process)), len(to_process))
            except Exception as e:
                logger.error("Error updating embeddings: %s", e)
                error_count += len(embedding_pairs)

    logger.info(
        "Complete. Updated=%d, Skipped=%d, Errors=%d",
        updated_count,
        skipped_count,
        error_count,
    )
    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
