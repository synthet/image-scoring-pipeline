from unittest.mock import MagicMock, patch
import os

from modules import db


def _mock_config(engine="firebird", dual_write=False):
    return {
        "engine": engine,
        "dual_write": dual_write,
    }


def test_get_db_firebird_default_engine(monkeypatch):
    """get_db() returns FirebirdConnectionProxy when engine=firebird."""
    fake_fb_conn = MagicMock()
    monkeypatch.setattr(
        db.config,
        "get_config_section",
        lambda name: _mock_config(engine="firebird", dual_write=False),
    )
    monkeypatch.setattr(db, "connect", lambda *args, **kwargs: fake_fb_conn)
    monkeypatch.setattr(db, "DB_PATH", "dummy.fdb")
    monkeypatch.setattr(db, "DEBUG_DB_CONNECTION", False)
    monkeypatch.setenv("FIREBIRD_USE_LOCAL_PATH", "1")

    conn = db.get_db()

    assert isinstance(conn, db.FirebirdConnectionProxy)


def test_get_db_postgres_primary_and_qmark_rows(monkeypatch):
    """get_db() returns PostgresConnectionProxy when engine=postgres,
    and the cursor proxy translates ? placeholders to %s."""
    class _Desc:
        def __init__(self, name):
            self.name = name

    class FakePGCursor:
        def __init__(self):
            self.executed = []
            self.description = [_Desc("id"), _Desc("file_name")]

        def execute(self, query, params=None):
            self.executed.append((query, params))

        def fetchone(self):
            return (7, "img.jpg")

        def fetchall(self):
            return []

    class FakePGConn:
        def __init__(self):
            self.cur = FakePGCursor()

        def cursor(self):
            return self.cur

        def commit(self):
            pass

        def rollback(self):
            pass

    fake_pg_conn = FakePGConn()
    release_calls = []

    monkeypatch.setattr(
        db.config,
        "get_config_section",
        lambda name: _mock_config(engine="postgres", dual_write=True),
    )
    monkeypatch.setattr(db.db_postgres, "get_pg_connection", lambda: fake_pg_conn)
    monkeypatch.setattr(db.db_postgres, "release_pg_connection", lambda conn: release_calls.append(conn))

    conn = db.get_db()
    assert isinstance(conn, db.PostgresConnectionProxy)

    cur = conn.cursor()
    cur.execute("SELECT id, file_name FROM images WHERE id = ?", (7,))
    row = cur.fetchone()

    assert fake_pg_conn.cur.executed[0][0].count("%s") == 1
    assert "?" not in fake_pg_conn.cur.executed[0][0]
    assert row["id"] == 7
    assert row["file_name"] == "img.jpg"
    conn.close()
    assert release_calls == [fake_pg_conn]


def test_postgres_proxy_translates_firebird_sql(monkeypatch):
    """PostgresCursorProxy applies full Firebird→PG translation
    (upsert, SELECT FIRST, DATEDIFF, etc.), not just ? → %s."""
    class _Desc:
        def __init__(self, name):
            self.name = name

    class FakePGCursor:
        def __init__(self):
            self.executed = []
            self.description = [_Desc("id")]

        def execute(self, query, params=None):
            self.executed.append((query, params))

        def fetchall(self):
            return []

    fake_cur = FakePGCursor()
    proxy = db.PostgresCursorProxy(fake_cur)

    proxy.execute("SELECT FIRST 10 id FROM images WHERE score > ?", (0.5,))
    translated = fake_cur.executed[0][0]

    assert "FIRST" not in translated
    assert "LIMIT 10" in translated
    assert "%s" in translated
    assert "?" not in translated


def test_dual_write_mode_gating(monkeypatch):
    """Dual-write is only enabled when engine=firebird AND dual_write=True."""
    queued = []
    monkeypatch.setattr(db._DUAL_WRITE_QUEUE, "put", lambda item: queued.append(item))

    monkeypatch.setattr(
        db.config,
        "get_config_section",
        lambda name: _mock_config(engine="postgres", dual_write=True),
    )
    db.init_dual_write()
    assert db._DUAL_WRITE_ENABLED is False
    db._enqueue_dual_write("INSERT INTO images(file_name) VALUES (?)", ("a.jpg",))
    assert queued == []

    monkeypatch.setattr(
        db.config,
        "get_config_section",
        lambda name: _mock_config(engine="firebird", dual_write=True),
    )
    db.init_dual_write()
    assert db._DUAL_WRITE_ENABLED is True
    db._enqueue_dual_write("INSERT INTO images(file_name) VALUES (?)", ("b.jpg",))
    assert len(queued) == 1


def test_dual_write_disabled_when_no_flag(monkeypatch):
    """Dual-write stays disabled when dual_write=False, even with engine=firebird."""
    monkeypatch.setattr(
        db.config,
        "get_config_section",
        lambda name: _mock_config(engine="firebird", dual_write=False),
    )
    db.init_dual_write()
    assert db._DUAL_WRITE_ENABLED is False
