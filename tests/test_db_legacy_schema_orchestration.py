from modules import db_legacy


class _Connection:
    def __init__(self) -> None:
        self.commits = 0
        self.closes = 0

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closes += 1


def test_init_db_impl_runs_extracted_schema_stages_in_order(monkeypatch):
    initial = _Connection()
    final = _Connection()
    connections = iter((initial, final))
    calls: list[str] = []
    cursor = object()

    monkeypatch.setattr(db_legacy, "get_db", lambda: next(connections))

    def base(conn, **_dependencies):
        assert conn is initial
        calls.append("base")
        return conn, cursor, ["id", "file_path"]

    def migrations(conn, actual_cursor, image_columns, **_dependencies):
        assert conn is initial
        assert actual_cursor is cursor
        assert image_columns == ["id", "file_path"]
        calls.append("migrations")
        return conn

    def integrity(conn, **_dependencies):
        assert conn is initial
        calls.append("integrity")
        return conn

    def keywords(conn, **_dependencies):
        assert conn is initial
        calls.append("keywords")
        return conn

    monkeypatch.setattr(db_legacy, "initialize_base_schema", base)
    monkeypatch.setattr(db_legacy, "run_additive_migrations", migrations)
    monkeypatch.setattr(db_legacy, "run_integrity_phase", integrity)
    monkeypatch.setattr(db_legacy, "run_keyword_phase", keywords)
    monkeypatch.setattr(
        db_legacy, "seed_pipeline_phases", lambda: calls.append("seed")
    )

    db_legacy._init_db_impl()

    assert calls == ["base", "migrations", "integrity", "keywords", "seed"]
    assert initial.closes == 1
    assert final.commits == 1
    assert final.closes == 1
