"""
FirebirdConnector — IConnector implementation wrapping db.get_db().

Uses the existing Firebird connection management in ``modules.db`` (DSN
resolution, WSL/Windows path handling, server auto-start, dual-write queue).
All SQL is written in Firebird dialect (``?`` placeholders); the connector
passes it through to ``FirebirdConnectionProxy`` / ``FirebirdCursorProxy``
which already handle the dual-write translation internally.

Import of ``modules.db`` is deferred to method bodies to avoid circular
imports at module load time (``db.py`` may later import from this package).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Sequence, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Transaction context
# ---------------------------------------------------------------------------

class _FbTx:
    """Transaction context for FirebirdConnector.run_transaction callbacks.

    All operations share the same ``FirebirdConnectionProxy``; the connector
    commits after the callback returns and rolls back on exception.
    """

    def __init__(self, conn) -> None:
        self._conn = conn

    def _cursor(self):
        return self._conn.cursor()

    def query(self, sql: str, params: Sequence | None = None) -> list[dict]:
        c = self._cursor()
        c.execute(sql, tuple(params) if params else None)
        return [dict(r) for r in c.fetchall()]

    def query_one(self, sql: str, params: Sequence | None = None) -> dict | None:
        c = self._cursor()
        c.execute(sql, tuple(params) if params else None)
        row = c.fetchone()
        return dict(row) if row else None

    def execute(self, sql: str, params: Sequence | None = None) -> int:
        c = self._cursor()
        c.execute(sql, tuple(params) if params else None)
        return int(getattr(c, 'affected_rows', None) or getattr(c, 'rowcount', 0) or 0)

    def execute_returning(self, sql: str, params: Sequence | None = None) -> list[dict]:
        c = self._cursor()
        c.execute(sql, tuple(params) if params else None)
        if c.description:
            return [dict(r) for r in c.fetchall()]
        return []


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------

class FirebirdConnector:
    """Connector that delegates to the Firebird backend via ``modules.db.get_db()``."""

    type = 'firebird'

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_conn(self):
        """Lazily acquire a connection to avoid circular imports."""
        from modules import db
        return db.get_db()

    # ------------------------------------------------------------------
    # IConnector
    # ------------------------------------------------------------------

    def query(self, sql: str, params: Sequence | None = None) -> list[dict]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(sql, tuple(params) if params else None)
            return [dict(r) for r in c.fetchall()]
        finally:
            conn.close()

    def query_one(self, sql: str, params: Sequence | None = None) -> dict | None:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(sql, tuple(params) if params else None)
            row = c.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def execute(self, sql: str, params: Sequence | None = None) -> int:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(sql, tuple(params) if params else None)
            rowcount = int(getattr(c, 'affected_rows', None) or getattr(c, 'rowcount', 0) or 0)
            conn.commit()
            return rowcount
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def execute_returning(self, sql: str, params: Sequence | None = None) -> list[dict]:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(sql, tuple(params) if params else None)
            result = [dict(r) for r in c.fetchall()] if c.description else []
            conn.commit()
            return result
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def execute_many(self, sql: str, params_list: list[Sequence]) -> None:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.executemany(sql, [tuple(p) for p in params_list])
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def run_transaction(self, callback: Callable[[_FbTx], T]) -> T:
        """Run callback inside a single Firebird connection/transaction."""
        conn = self._get_conn()
        try:
            result = callback(_FbTx(conn))
            conn.commit()
            return result
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def check_connection(self) -> bool:
        try:
            self.query("SELECT 1 FROM RDB$DATABASE")
            return True
        except Exception as e:
            logger.warning("Firebird connection check failed: %s", e)
            return False

    def verify_startup(self) -> bool:
        return self.check_connection()

    def close(self) -> None:
        # Connections are per-operation; nothing to release globally.
        pass
