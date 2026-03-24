import os
import sys
import types

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Lightweight stubs so script import works in minimal test environments.
if "psycopg2" not in sys.modules:
    psycopg2_stub = types.ModuleType("psycopg2")
    extras_stub = types.ModuleType("psycopg2.extras")
    extras_stub.RealDictCursor = object
    psycopg2_stub.extras = extras_stub
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.extras"] = extras_stub

if "pgvector.psycopg2" not in sys.modules:
    pgvector_stub = types.ModuleType("pgvector")
    pgvector_psycopg2_stub = types.ModuleType("pgvector.psycopg2")
    pgvector_psycopg2_stub.register_vector = lambda *_args, **_kwargs: None
    pgvector_stub.psycopg2 = pgvector_psycopg2_stub
    sys.modules["pgvector"] = pgvector_stub
    sys.modules["pgvector.psycopg2"] = pgvector_psycopg2_stub

from scripts.python import migrate_firebird_to_postgres as migration


class _RecordingCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))


class _RecordingConn:
    def __init__(self):
        self._cursor = _RecordingCursor()
        self.commits = 0

    def cursor(self, *args, **kwargs):
        return self._cursor

    def commit(self):
        self.commits += 1


class _SkipCursor:
    def execute(self, sql, params=None):
        self.last_sql = sql

    def fetchone(self):
        return [3]


class _SkipConn:
    def __init__(self):
        self._cursor = _SkipCursor()

    def cursor(self, *args, **kwargs):
        return self._cursor

    def commit(self):
        raise AssertionError("commit should not be called on skip path")


def test_parser_has_clear_target_flag():
    parser = migration.build_parser()

    args = parser.parse_args(["--clear-target"])

    assert hasattr(args, "clear_target")
    assert args.clear_target is True


def test_clear_target_tables_uses_reverse_dependency_order():
    conn = _RecordingConn()
    tables = ["jobs", "images", "image_phase_status"]

    migration.clear_target_tables(conn, tables)

    assert [sql for sql, _ in conn._cursor.executed] == [
        "DELETE FROM image_phase_status",
        "DELETE FROM images",
        "DELETE FROM jobs",
    ]
    assert conn.commits == 1


def test_migrate_table_skips_non_empty_target_when_not_cleared(monkeypatch):
    monkeypatch.setattr(migration, "table_exists_fb", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(migration, "table_exists_pg", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(migration, "get_fb_columns", lambda *_args, **_kwargs: ["id"])
    monkeypatch.setattr(migration, "get_pg_columns", lambda *_args, **_kwargs: ["id"])

    fb_conn = _SkipConn()
    pg_conn = _SkipConn()

    migrated = migration.migrate_table(fb_conn, pg_conn, "jobs")

    assert migrated == 0
