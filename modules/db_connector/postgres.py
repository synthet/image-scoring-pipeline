"""
PostgresConnector — IConnector implementation wrapping db_postgres.py.

Uses the psycopg2 connection pool managed by ``modules.db_postgres``.
SQL is expected in Firebird dialect (``?`` placeholders); this connector
translates via ``modules.db._translate_fb_to_pg`` before execution so that
callers can write a single SQL dialect regardless of the active engine.

Both ``modules.db_postgres`` and ``modules.db._translate_fb_to_pg`` are
imported lazily to avoid circular-import issues.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Sequence, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _translate(sql: str) -> str:
    """Translate Firebird SQL dialect to PostgreSQL (lazy import)."""
    from modules.db import _translate_fb_to_pg
    return _translate_fb_to_pg(sql)


# ---------------------------------------------------------------------------
# Transaction context
# ---------------------------------------------------------------------------

class _PgTx:
    """Transaction context for PostgresConnector.run_transaction callbacks.

    Wraps a single pooled psycopg2 connection; the connector commits after the
    callback returns normally and rolls back on exception.
    """

    def __init__(self, conn) -> None:
        self._conn = conn

    def query(self, sql: str, params: Sequence | None = None) -> list[dict]:
        import psycopg2.extras
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_translate(sql), tuple(params) if params else None)
            return [dict(r) for r in cur.fetchall()]

    def query_one(self, sql: str, params: Sequence | None = None) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Sequence | None = None) -> int:
        with self._conn.cursor() as cur:
            cur.execute(_translate(sql), tuple(params) if params else None)
            return cur.rowcount

    def execute_returning(self, sql: str, params: Sequence | None = None) -> list[dict]:
        import psycopg2.extras
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_translate(sql), tuple(params) if params else None)
            if cur.description:
                return [dict(r) for r in cur.fetchall()]
            return []


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------

class PostgresConnector:
    """Connector that uses the psycopg2 pool in ``modules.db_postgres``."""

    type = 'postgres'

    # ------------------------------------------------------------------
    # IConnector
    # ------------------------------------------------------------------

    def query(self, sql: str, params: Sequence | None = None) -> list[dict]:
        from modules import db_postgres
        return db_postgres.execute_select(
            _translate(sql), tuple(params) if params else None
        )

    def query_one(self, sql: str, params: Sequence | None = None) -> dict | None:
        from modules import db_postgres
        row = db_postgres.execute_select_one(
            _translate(sql), tuple(params) if params else None
        )
        return dict(row) if row else None

    def execute(self, sql: str, params: Sequence | None = None) -> int:
        from modules import db_postgres
        return db_postgres.execute_write(
            _translate(sql), tuple(params) if params else None
        )

    def execute_returning(self, sql: str, params: Sequence | None = None) -> list[dict]:
        import psycopg2.extras
        from modules import db_postgres
        pg_sql = _translate(sql)
        with db_postgres.PGConnectionManager(commit=True) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(pg_sql, tuple(params) if params else None)
                if cur.description:
                    return [dict(r) for r in cur.fetchall()]
                return []

    def execute_many(self, sql: str, params_list: list[Sequence]) -> None:
        from modules import db_postgres
        pg_sql = _translate(sql)
        with db_postgres.PGConnectionManager(commit=True) as conn:
            with conn.cursor() as cur:
                cur.executemany(pg_sql, [tuple(p) for p in params_list])

    def run_transaction(self, callback: Callable[[_PgTx], T]) -> T:
        """Run callback inside a single PostgreSQL transaction."""
        from modules import db_postgres
        with db_postgres.PGConnectionManager(commit=False) as conn:
            try:
                result = callback(_PgTx(conn))
                conn.commit()
                return result
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

    def check_connection(self) -> bool:
        try:
            self.query("SELECT 1")
            return True
        except Exception as e:
            logger.warning("PostgreSQL connection check failed: %s", e)
            return False

    def verify_startup(self) -> bool:
        return self.check_connection()

    def close(self) -> None:
        # Connection pool is managed globally by db_postgres; nothing to release here.
        pass
