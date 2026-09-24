#!/usr/bin/env python3
"""Export a stratified cohort manifest from PostgreSQL (read-only).

Samples ``per_quintile`` images from each ``score_general`` NTILE bucket among rows
with non-null composites and at least ``min_core_models`` successful core IQA models.

Run in gpu-shell when DB is reachable::

    scripts/batch/docker_gpu_run.bat scripts/research/everypixel_correlation/export_cohort.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.research.everypixel_correlation.common import (
    CORE_MODEL_NAMES,
    DEFAULT_MANIFEST,
    REPORTS_DIR,
)

logger = logging.getLogger(__name__)


def _cohort_sql(min_core_models: int) -> str:
    placeholders = ", ".join("?" for _ in CORE_MODEL_NAMES)
    return f"""
        WITH base AS (
            SELECT
                i.id AS image_id,
                i.file_path,
                i.score_general,
                i.score_technical,
                i.score_aesthetic,
                i.rating,
                i.label,
                i.folder_id
            FROM images i
            WHERE i.score_general IS NOT NULL
              AND i.score_general > 0
              AND i.file_path IS NOT NULL
              AND BTRIM(i.file_path) <> ''
        ),
        quintiles AS (
            SELECT
                b.*,
                NTILE(5) OVER (ORDER BY b.score_general) AS general_quintile
            FROM base b
        ),
        core_counts AS (
            SELECT
                ims.image_id,
                COUNT(DISTINCT ims.model_name) AS core_model_count
            FROM image_model_scores ims
            WHERE ims.model_name IN ({placeholders})
              AND ims.status = 'success'
              AND COALESCE(ims.is_shadow, FALSE) = FALSE
            GROUP BY ims.image_id
        )
        SELECT q.*
        FROM quintiles q
        JOIN core_counts c ON c.image_id = q.image_id
        WHERE c.core_model_count >= ?
        ORDER BY q.general_quintile, q.image_id
    """


def _load_eligible(min_core_models: int) -> list[dict[str, Any]]:
    from modules import db

    db.init_db()
    params = (*CORE_MODEL_NAMES, min_core_models)
    rows = db.get_connector().query(_cohort_sql(min_core_models), params) or []
    return [dict(r) for r in rows]


def _stratified_sample(
    rows: list[dict[str, Any]],
    *,
    per_quintile: int,
    seed: int,
) -> list[dict[str, Any]]:
    by_q: dict[int, list[dict[str, Any]]] = {q: [] for q in range(1, 6)}
    for row in rows:
        q = int(row["general_quintile"])
        if 1 <= q <= 5:
            by_q[q].append(row)
    rng = random.Random(seed)
    picked: list[dict[str, Any]] = []
    for q in range(1, 6):
        pool = by_q[q]
        rng.shuffle(pool)
        picked.extend(pool[:per_quintile])
    return sorted(picked, key=lambda r: (int(r["general_quintile"]), int(r["image_id"])))


def _manifest_id(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def export_cohort(
    *,
    per_quintile: int,
    seed: int,
    min_core_models: int,
    require_file: bool,
    out_path: Path,
) -> Path:
    eligible = _load_eligible(min_core_models)
    if not eligible:
        raise SystemExit("No eligible images in database (check Postgres and scoring coverage).")

    sampled = _stratified_sample(eligible, per_quintile=per_quintile, seed=seed)
    if require_file:
        kept = [r for r in sampled if Path(str(r["file_path"])).is_file()]
        missing = len(sampled) - len(kept)
        if missing:
            logger.warning("Dropped %d rows with missing files on disk", missing)
        sampled = kept

    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "per_quintile": per_quintile,
        "min_core_models": min_core_models,
        "require_file": require_file,
        "eligible_count": len(eligible),
        "sample_count": len(sampled),
        "core_model_names": list(CORE_MODEL_NAMES),
    }
    manifest = {"manifest_id": _manifest_id({**meta, "n": len(sampled)}), **meta, "images": sampled}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %s (%d images)", out_path, len(sampled))
    return out_path


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Export Everypixel study cohort manifest")
    parser.add_argument("--per-quintile", type=int, default=80, help="Images per score_general quintile")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--min-core-models",
        type=int,
        default=4,
        help="Min distinct core models (liqe/spaq/ava/topiq/arniqa) with success",
    )
    parser.add_argument(
        "--require-file",
        action="store_true",
        help="Drop manifest rows whose file_path is missing on disk",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    export_cohort(
        per_quintile=args.per_quintile,
        seed=args.seed,
        min_core_models=args.min_core_models,
        require_file=args.require_file,
        out_path=args.out,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
