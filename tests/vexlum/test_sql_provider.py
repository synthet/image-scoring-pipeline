"""db.* provider + SQL executor: read-only gate, single statement, rollback on dry run, tiers."""

from __future__ import annotations

import pytest

from modules.mcp.actions.errors import McpActionError, ValidationError
from modules.vexlum import catalog, service
from modules.vexlum.executors import sql


class _FakeCursor:
    def __init__(self, rows, columns, rowcount=None):
        self.executed: list[tuple[str, object]] = []
        self._rows = rows
        self.description = [(c,) for c in columns] if columns else None
        self.rowcount = len(rows) if rowcount is None else rowcount
        self.statusmessage = "OK"

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchmany(self, n):
        return self._rows[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


@pytest.fixture
def fake_pg(monkeypatch):
    """Replace the pool with a fake connection; record the commit flag of each checkout."""
    from modules import db_postgres

    state: dict = {"commits": [], "cursor": _FakeCursor([(1,), (2,), (3,)], ["x"])}

    class _Manager:
        def __init__(self, commit=False):
            state["commits"].append(commit)

        def __enter__(self):
            return _FakeConn(state["cursor"])

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(db_postgres, "PGConnectionManager", _Manager)
    monkeypatch.setattr(sql, "_ensure_db", lambda: None)
    return state


# --------------------------------------------------------------------------- catalog / tiers


def test_db_actions_and_tiers():
    by_id = catalog.get_catalog()["by_id"]
    assert by_id["db.schema"]["tier"] == "read"
    assert by_id["db.query"]["tier"] == "read"
    assert by_id["db.execute"]["tier"] == "destructive"


def test_db_execute_real_run_refused_without_confirmation():
    out = service.execute("db.execute", {"query": "DELETE FROM images WHERE id = -1"})
    assert out["status"] == "error"
    assert out["code"] == "confirmation_required"


# --------------------------------------------------------------------------- db.query gate


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM images",
        "UPDATE images SET score = 0",
        "INSERT INTO jobs (id) VALUES (1)",
        "DROP TABLE images",
        "SELECT 1; DELETE FROM images",
    ],
)
def test_query_rejects_writes_and_multi_statement(query, fake_pg):
    with pytest.raises(ValidationError):
        sql.run_query({"query": query})
    assert fake_pg["commits"] == []  # rejected before any connection


def test_query_rejects_empty(fake_pg):
    with pytest.raises(ValidationError):
        sql.run_query({"query": "  -- only a comment"})
    assert fake_pg["commits"] == []


def test_query_select_is_read_only_and_truncates(fake_pg):
    out = sql.run_query({"query": "SELECT x FROM t WHERE y = %s;", "params": [5], "max_rows": 2})
    cur = fake_pg["cursor"]
    assert cur.executed[0] == ("SET TRANSACTION READ ONLY", None)
    assert cur.executed[1] == ("SELECT x FROM t WHERE y = %s", (5,))
    assert out["columns"] == ["x"]
    assert out["rows"] == [{"x": 1}, {"x": 2}]
    assert out["truncated"] is True
    assert fake_pg["commits"] == [False]


def test_query_accepts_with_cte(fake_pg):
    out = sql.run_query({"query": "WITH a AS (SELECT 1 AS x) SELECT x FROM a"})
    assert out["row_count"] == 3


# --------------------------------------------------------------------------- db.execute


def test_execute_dry_run_rolls_back(fake_pg):
    fake_pg["cursor"] = _FakeCursor([], [], rowcount=7)
    out = sql.run_execute({"query": "UPDATE images SET score = 0 WHERE id < 8"}, dry_run=True)
    assert fake_pg["commits"] == [False]
    assert out["rowcount"] == 7
    assert out["committed"] is False
    assert out["rolled_back"] is True


def test_execute_real_run_commits(fake_pg):
    fake_pg["cursor"] = _FakeCursor([(42,)], ["id"], rowcount=1)
    out = sql.run_execute({"query": "DELETE FROM jobs WHERE id = %s RETURNING id", "params": [42]}, dry_run=False)
    assert fake_pg["commits"] == [True]
    assert out["committed"] is True
    assert "rolled_back" not in out
    assert out["rows"] == [{"id": 42}]


def test_execute_rejects_multi_statement(fake_pg):
    with pytest.raises(ValidationError):
        sql.run_execute({"query": "DELETE FROM a; DELETE FROM b"}, dry_run=True)
    assert fake_pg["commits"] == []


def test_ensure_db_requires_postgres(monkeypatch):
    from modules import config

    monkeypatch.setattr(config, "get_database_engine", lambda: "firebird")
    with pytest.raises(McpActionError, match="postgres"):
        sql._ensure_db()


# --------------------------------------------------------------------------- live PostgreSQL


@pytest.mark.db
def test_live_query_and_dry_run_rollback():
    out = service.execute("db.query", {"query": "SELECT 1 AS ok"})
    assert out["status"] == "success", out
    assert out["data"]["rows"] == [{"ok": 1}]

    dry = service.execute("db.execute", {"query": "CREATE TEMP TABLE vexlum_probe AS SELECT 1 AS x"}, dry_run=True)
    assert dry["status"] == "success", dry
    assert dry["data"]["preview"]["rolled_back"] is True
    assert dry["data"]["preview"]["committed"] is False
    assert dry["data"]["confirm_token"]
