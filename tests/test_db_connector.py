"""
Unit tests for modules/db_connector/.

Tests the connector protocol, factory, and each implementation using mocks
— no live database connection required (no 'db' or 'firebird' pytest markers).

Markers used:
    (none) — all tests run in the fast subset
"""
from __future__ import annotations

import sys
import threading
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# IConnector protocol structural check
# ---------------------------------------------------------------------------

class TestIConnectorProtocol:
    """Verify that the Protocol is structurally sound and runtime-checkable."""

    def test_protocol_is_importable(self):
        from modules.db_connector.protocol import IConnector, ITransaction
        assert IConnector is not None
        assert ITransaction is not None

    def test_minimal_implementation_satisfies_protocol(self):
        from modules.db_connector.protocol import IConnector

        class _Minimal:
            type = 'firebird'
            def query(self, sql, params=None): return []
            def query_one(self, sql, params=None): return None
            def execute(self, sql, params=None): return 0
            def execute_returning(self, sql, params=None): return []
            def execute_many(self, sql, params_list=None): pass
            def run_transaction(self, callback): return callback(MagicMock())
            def check_connection(self): return True
            def verify_startup(self): return True
            def close(self): pass

        assert isinstance(_Minimal(), IConnector)

    def test_incomplete_implementation_does_not_satisfy_protocol(self):
        from modules.db_connector.protocol import IConnector

        class _Incomplete:
            type = 'firebird'
            def query(self, sql, params=None): return []
            # missing all other methods

        assert not isinstance(_Incomplete(), IConnector)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestFactory:
    """Verify get_connector() returns the right type per config."""

    def setup_method(self):
        from modules.db_connector import reset_connector
        reset_connector()

    def teardown_method(self):
        from modules.db_connector import reset_connector
        reset_connector()

    def _patch_engine(self, engine: str):
        """Patch modules.config.get_config_section to return the given engine."""
        cfg = {"engine": engine, "api_url": "http://localhost:7860"}
        return patch("modules.config.get_config_section", return_value=cfg)

    def test_default_returns_firebird(self):
        from modules.db_connector import get_connector, reset_connector
        from modules.db_connector.firebird import FirebirdConnector

        with patch("modules.config.get_config_section", return_value={}):
            conn = get_connector()

        assert isinstance(conn, FirebirdConnector)

    def test_engine_firebird(self):
        from modules.db_connector import get_connector
        from modules.db_connector.firebird import FirebirdConnector

        with self._patch_engine("firebird"):
            conn = get_connector()

        assert isinstance(conn, FirebirdConnector)

    def test_engine_postgres(self):
        from modules.db_connector import get_connector
        from modules.db_connector.postgres import PostgresConnector

        with self._patch_engine("postgres"):
            conn = get_connector()

        assert isinstance(conn, PostgresConnector)

    def test_engine_api(self):
        from modules.db_connector import get_connector
        from modules.db_connector.api import ApiConnector

        with self._patch_engine("api"):
            conn = get_connector()

        assert isinstance(conn, ApiConnector)
        assert conn._base_url == "http://localhost:7860"

    def test_unknown_engine_falls_back_to_postgres(self):
        from modules.db_connector import get_connector
        from modules.db_connector.postgres import PostgresConnector

        with self._patch_engine("sqlite"):
            conn = get_connector()

        assert isinstance(conn, PostgresConnector)

    def test_singleton(self):
        from modules.db_connector import get_connector
        from modules.db_connector.firebird import FirebirdConnector

        with self._patch_engine("firebird"):
            a = get_connector()
            b = get_connector()

        assert a is b

    def test_reset_clears_singleton(self):
        from modules.db_connector import get_connector, reset_connector
        from modules.db_connector.firebird import FirebirdConnector
        from modules.db_connector.postgres import PostgresConnector

        with self._patch_engine("firebird"):
            a = get_connector()

        reset_connector()

        with self._patch_engine("postgres"):
            b = get_connector()

        assert isinstance(a, FirebirdConnector)
        assert isinstance(b, PostgresConnector)

    def test_thread_safety(self):
        """Multiple threads calling get_connector() must all get the same instance."""
        from modules.db_connector import get_connector

        results = []
        errors = []

        def _worker():
            try:
                results.append(get_connector())
            except Exception as e:
                errors.append(e)

        with self._patch_engine("firebird"):
            threads = [threading.Thread(target=_worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert not errors
        assert len(results) == 10
        assert len(set(id(r) for r in results)) == 1  # all same instance


# ---------------------------------------------------------------------------
# FirebirdConnector (mocked)
# ---------------------------------------------------------------------------

class _FakeRow:
    """Minimal RowWrapper-like stub: dict(row) yields the given data."""
    def __init__(self, data: dict) -> None:
        self._data = data
    def __iter__(self):
        return iter(self._data.items())
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self._data.values())[key]
        return self._data[key]


class TestFirebirdConnector:
    """FirebirdConnector with a mocked db.get_db() connection."""

    def _make_row(self, data: dict) -> _FakeRow:
        return _FakeRow(data)

    def _mock_conn(self):
        conn = MagicMock()
        return conn

    def test_query_returns_list_of_dicts(self):
        from modules.db_connector.firebird import FirebirdConnector

        row = self._make_row({"id": 1, "name": "test"})
        cursor = MagicMock()
        cursor.fetchall.return_value = [row]
        cursor.description = [("id",), ("name",)]

        conn = self._mock_conn()
        conn.cursor.return_value = cursor

        fc = FirebirdConnector()
        with patch.object(fc, "_get_conn", return_value=conn):
            result = fc.query("SELECT * FROM images WHERE id = ?", (1,))

        assert result == [{"id": 1, "name": "test"}]
        cursor.execute.assert_called_once_with("SELECT * FROM images WHERE id = ?", (1,))
        conn.close.assert_called_once()

    def test_query_one_returns_first_row(self):
        from modules.db_connector.firebird import FirebirdConnector

        row = self._make_row({"id": 42})
        cursor = MagicMock()
        cursor.fetchone.return_value = row

        conn = self._mock_conn()
        conn.cursor.return_value = cursor

        fc = FirebirdConnector()
        with patch.object(fc, "_get_conn", return_value=conn):
            result = fc.query_one("SELECT * FROM images WHERE id = ?", (42,))

        assert result == {"id": 42}

    def test_query_one_returns_none_when_empty(self):
        from modules.db_connector.firebird import FirebirdConnector

        cursor = MagicMock()
        cursor.fetchone.return_value = None

        conn = self._mock_conn()
        conn.cursor.return_value = cursor

        fc = FirebirdConnector()
        with patch.object(fc, "_get_conn", return_value=conn):
            result = fc.query_one("SELECT * FROM images WHERE id = ?", (999,))

        assert result is None

    def test_execute_commits_and_returns_rowcount(self):
        from modules.db_connector.firebird import FirebirdConnector

        cursor = MagicMock()
        cursor.affected_rows = 3

        conn = self._mock_conn()
        conn.cursor.return_value = cursor

        fc = FirebirdConnector()
        with patch.object(fc, "_get_conn", return_value=conn):
            count = fc.execute("UPDATE images SET rating = ? WHERE id = ?", (5, 1))

        assert count == 3
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_execute_rollbacks_on_exception(self):
        from modules.db_connector.firebird import FirebirdConnector

        cursor = MagicMock()
        cursor.execute.side_effect = RuntimeError("DB error")

        conn = self._mock_conn()
        conn.cursor.return_value = cursor

        fc = FirebirdConnector()
        with patch.object(fc, "_get_conn", return_value=conn):
            with pytest.raises(RuntimeError, match="DB error"):
                fc.execute("UPDATE images SET rating = ? WHERE id = ?", (5, 1))

        conn.rollback.assert_called_once()
        conn.close.assert_called_once()

    def test_execute_returning_returns_rows(self):
        from modules.db_connector.firebird import FirebirdConnector

        row = self._make_row({"id": 10})
        cursor = MagicMock()
        cursor.description = [("id",)]
        cursor.fetchall.return_value = [row]

        conn = self._mock_conn()
        conn.cursor.return_value = cursor

        fc = FirebirdConnector()
        with patch.object(fc, "_get_conn", return_value=conn):
            result = fc.execute_returning(
                "INSERT INTO jobs (status) VALUES (?) RETURNING id", ("queued",)
            )

        assert result == [{"id": 10}]
        conn.commit.assert_called_once()

    def test_run_transaction_commits_on_success(self):
        from modules.db_connector.firebird import FirebirdConnector

        cursor = MagicMock()
        cursor.fetchall.return_value = []
        cursor.description = None

        conn = self._mock_conn()
        conn.cursor.return_value = cursor

        fc = FirebirdConnector()
        with patch.object(fc, "_get_conn", return_value=conn):
            result = fc.run_transaction(lambda tx: "done")

        assert result == "done"
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()

    def test_run_transaction_rollbacks_on_exception(self):
        from modules.db_connector.firebird import FirebirdConnector

        conn = self._mock_conn()

        fc = FirebirdConnector()
        with patch.object(fc, "_get_conn", return_value=conn):
            with pytest.raises(ValueError, match="oops"):
                fc.run_transaction(lambda tx: (_ for _ in ()).throw(ValueError("oops")))

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_check_connection_returns_true_on_success(self):
        from modules.db_connector.firebird import FirebirdConnector

        fc = FirebirdConnector()
        with patch.object(fc, "query", return_value=[{"1": 1}]):
            assert fc.check_connection() is True

    def test_check_connection_returns_false_on_error(self):
        from modules.db_connector.firebird import FirebirdConnector

        fc = FirebirdConnector()
        with patch.object(fc, "query", side_effect=Exception("no db")):
            assert fc.check_connection() is False


# ---------------------------------------------------------------------------
# ApiConnector (mocked requests.Session)
# ---------------------------------------------------------------------------

class TestApiConnector:
    """ApiConnector with a mocked requests.Session."""

    def _make_connector(self, write_token: str = ""):
        from modules.db_connector.api import ApiConnector
        conn = ApiConnector(base_url="http://test:7860", write_token=write_token)
        conn._session = MagicMock()
        return conn

    def _mock_response(self, data: dict):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = data
        resp.raise_for_status = MagicMock()
        return resp

    def test_query_calls_correct_endpoint(self):
        conn = self._make_connector()
        conn._session.post.return_value = self._mock_response(
            {"rows": [{"id": 1}], "rowcount": 1}
        )

        rows = conn.query("SELECT * FROM images WHERE id = ?", (1,))

        conn._session.post.assert_called_once_with(
            "http://test:7860/api/db/query",
            json={"sql": "SELECT * FROM images WHERE id = ?", "params": [1], "write": False},
            timeout=30.0,
        )
        assert rows == [{"id": 1}]

    def test_execute_sends_write_flag(self):
        conn = self._make_connector()
        conn._session.post.return_value = self._mock_response(
            {"rows": [], "rowcount": 1}
        )

        count = conn.execute("UPDATE images SET rating = ? WHERE id = ?", (5, 1))

        call_kwargs = conn._session.post.call_args
        assert call_kwargs.kwargs["json"]["write"] is True
        assert "headers" not in call_kwargs.kwargs
        assert count == 1

    def test_execute_sends_x_db_write_token_when_configured(self):
        conn = self._make_connector(write_token="secret-token")
        conn._session.post.return_value = self._mock_response(
            {"rows": [], "rowcount": 1}
        )

        conn.execute("UPDATE images SET rating = ? WHERE id = ?", (5, 1))

        call_kwargs = conn._session.post.call_args.kwargs
        assert call_kwargs["headers"] == {"X-DB-Write-Token": "secret-token"}

    def test_run_transaction_sends_token_on_batch_when_configured(self):
        conn = self._make_connector(write_token="tok")
        conn._session.post.return_value = self._mock_response({"ok": True})

        def _cb(tx):
            tx.execute("UPDATE jobs SET status = ? WHERE id = ?", ("done", 1))

        conn.run_transaction(_cb)

        call_kwargs = conn._session.post.call_args.kwargs
        assert call_kwargs["headers"] == {"X-DB-Write-Token": "tok"}

    def test_check_connection_pings_endpoint(self):
        conn = self._make_connector()
        resp = MagicMock()
        resp.status_code = 200
        conn._session.get.return_value = resp

        assert conn.check_connection() is True
        conn._session.get.assert_called_once_with(
            "http://test:7860/api/db/ping", timeout=5.0
        )

    def test_check_connection_returns_false_on_http_error(self):
        conn = self._make_connector()
        conn._session.get.side_effect = Exception("connection refused")

        assert conn.check_connection() is False

    def test_query_one_returns_first_row(self):
        conn = self._make_connector()
        conn._session.post.return_value = self._mock_response(
            {"rows": [{"id": 7}, {"id": 8}], "rowcount": 2}
        )

        row = conn.query_one("SELECT * FROM images WHERE id = ?", (7,))
        assert row == {"id": 7}

    def test_query_one_returns_none_on_empty(self):
        conn = self._make_connector()
        conn._session.post.return_value = self._mock_response(
            {"rows": [], "rowcount": 0}
        )

        row = conn.query_one("SELECT * FROM images WHERE id = ?", (999,))
        assert row is None

    def test_run_transaction_sends_batch(self):
        conn = self._make_connector()
        conn._session.post.return_value = self._mock_response({"ok": True})

        def _cb(tx):
            tx.execute("UPDATE jobs SET status = ? WHERE id = ?", ("done", 1))
            tx.execute("UPDATE jobs SET status = ? WHERE id = ?", ("done", 2))

        conn.run_transaction(_cb)

        # Last post should be the /transaction batch
        last_call = conn._session.post.call_args
        assert "/api/db/transaction" in last_call.args[0]
        stmts = last_call.kwargs["json"]["statements"]
        assert len(stmts) == 2

    def test_close_closes_session(self):
        conn = self._make_connector()
        session = conn._session

        conn.close()

        session.close.assert_called_once()
        assert conn._session is None


# ---------------------------------------------------------------------------
# PostgresConnector (mocked db_postgres)
# ---------------------------------------------------------------------------

class TestPostgresConnector:
    """PostgresConnector with mocked db_postgres helpers."""

    @staticmethod
    def _clear_modules_db_postgres_stale() -> None:
        import modules as _m

        if hasattr(_m, "db_postgres"):
            delattr(_m, "db_postgres")

    def test_query_delegates_to_execute_select(self):
        from modules.db_connector.postgres import PostgresConnector

        try:
            with patch("modules.db_postgres.execute_select", return_value=[{"id": 1}]) as mock_sel:
                pc = PostgresConnector()
                with patch("modules.db_connector.postgres._translate", side_effect=lambda s: s):
                    rows = pc.query("SELECT * FROM images WHERE id = ?", (1,))
        finally:
            self._clear_modules_db_postgres_stale()

        mock_sel.assert_called_once_with("SELECT * FROM images WHERE id = ?", (1,))
        assert rows == [{"id": 1}]

    def test_execute_delegates_to_execute_write(self):
        from modules.db_connector.postgres import PostgresConnector

        try:
            with patch("modules.db_postgres.execute_write", return_value=2) as mock_w:
                pc = PostgresConnector()
                with patch("modules.db_connector.postgres._translate", side_effect=lambda s: s):
                    count = pc.execute("UPDATE images SET rating = ? WHERE id = ?", (5, 1))
        finally:
            self._clear_modules_db_postgres_stale()

        mock_w.assert_called_once_with(
            "UPDATE images SET rating = ? WHERE id = ?", (5, 1)
        )
        assert count == 2

    def test_check_connection_returns_true_on_success(self):
        from modules.db_connector.postgres import PostgresConnector

        pc = PostgresConnector()
        with patch.object(pc, "query", return_value=[{"?column?": 1}]):
            assert pc.check_connection() is True

    def test_check_connection_returns_false_on_error(self):
        from modules.db_connector.postgres import PostgresConnector

        pc = PostgresConnector()
        with patch.object(pc, "query", side_effect=Exception("no pg")):
            assert pc.check_connection() is False
