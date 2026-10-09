"""Migration 0041 (``images.registered_at``, #584): backfill before default, DDL parity."""

import pytest

pytestmark = [pytest.mark.postgres]


def _column(conn):
    return conn.query_one(
        "SELECT data_type, column_default FROM information_schema.columns "
        "WHERE table_name = 'images' AND column_name = 'registered_at'"
    )


def test_upgrade_0041_backfills_from_created_at_then_defaults(postgres_test_session, clean_postgres):
    from alembic import command
    from alembic.config import Config

    from modules import db

    conn = db.get_connector()
    runtime = _column(conn)  # what init_db() produces
    conn.execute("ALTER TABLE images DROP COLUMN registered_at")  # back to the 0040 shape
    old_id = conn.execute_returning(
        "INSERT INTO images (file_path, created_at) VALUES ('/a.jpg', '2019-07-17 11:00:24') RETURNING id"
    )[0]["id"]

    cfg = Config("alembic.ini")
    command.stamp(cfg, "0040")
    command.upgrade(cfg, "0041")
    command.upgrade(cfg, "0041")  # idempotent

    row = conn.query_one("SELECT created_at, registered_at FROM images WHERE id = ?", (old_id,))
    assert row["registered_at"] == row["created_at"]  # not stamped with the upgrade time
    assert _column(conn) == runtime
    new = conn.execute_returning(
        "INSERT INTO images (file_path, created_at) VALUES ('/b.jpg', '2019-07-17 11:00:24') RETURNING registered_at"
    )[0]
    assert new["registered_at"] > row["created_at"]
