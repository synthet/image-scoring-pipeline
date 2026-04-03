"""
Registry of embedding / vector spaces stored in PostgreSQL (pgvector).

Each space has a fixed dimension; different dimensions use separate physical
storage (see docs/plans/database/DB_VECTORS_REFACTOR.md). Firebird remains
single-blob on ``images.image_embedding`` until gallery migrates to Postgres.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_SPACE_CODE = "mobilenet_v2_imagenet_gap"
DEFAULT_EMBEDDING_MODEL_DIM = 1280

_space_id_cache: int | None = None


def get_default_embedding_space_id() -> int | None:
    global _space_id_cache
    if _space_id_cache is not None:
        return _space_id_cache
    try:
        from modules import db
        from modules import db_postgres

        if db._get_db_engine() != "postgres":
            return None
        row = db_postgres.execute_select_one(
            "SELECT id FROM embedding_spaces WHERE code = %s AND COALESCE(active, 1) = 1 LIMIT 1",
            (DEFAULT_EMBEDDING_SPACE_CODE,),
        )
        _space_id_cache = int(row["id"]) if row else None
        return _space_id_cache
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning(f"Failed to load default embedding space: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error loading default embedding space: {e}")
        return None


def invalidate_default_embedding_space_cache() -> None:
    global _space_id_cache
    _space_id_cache = None
