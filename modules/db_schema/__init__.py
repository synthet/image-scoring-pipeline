"""Ordered PostgreSQL schema initialization helpers.

Each helper receives the cursor owned by :mod:`modules.db_postgres` so the
entire bootstrap remains one transaction and preserves the historical DDL order.
"""

from modules.db_schema.core import initialize_core_schema
from modules.db_schema.embeddings import initialize_embedding_schema
from modules.db_schema.pipeline import initialize_pipeline_schema
from modules.db_schema.review import initialize_review_schema


def initialize_schema(
    cur,
    *,
    conn,
    default_embedding_space_sql: str,
    extra_embedding_spaces_sql: tuple[str, ...] | list[str],
) -> None:
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    initialize_core_schema(cur)
    initialize_embedding_schema(
        cur,
        default_embedding_space_sql=default_embedding_space_sql,
        extra_embedding_spaces_sql=extra_embedding_spaces_sql,
    )
    initialize_pipeline_schema(cur)
    initialize_review_schema(cur, conn=conn)
