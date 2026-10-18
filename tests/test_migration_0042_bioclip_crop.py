"""Migration 0042 (``bioclip_2_crop`` embedding space, #641): idempotent upgrade, clean downgrade."""

import pytest

pytestmark = [pytest.mark.postgres]

_CODE = "bioclip_2_crop"


def _space(conn):
    return conn.query_one("SELECT dim, active FROM embedding_spaces WHERE code = ?", (_CODE,))


def test_upgrade_0042_registers_crop_space_and_downgrade_removes_it(postgres_test_session, clean_postgres):
    from alembic import command
    from alembic.config import Config

    from modules import db

    conn = db.get_connector()
    assert _space(conn) is not None  # init_db() seeds it, matching the migration

    cfg = Config("alembic.ini")
    command.stamp(cfg, "0042")
    command.downgrade(cfg, "0041")
    assert _space(conn) is None

    command.upgrade(cfg, "0042")
    command.stamp(cfg, "0041")
    command.upgrade(cfg, "0042")  # idempotent: no duplicate row
    row = _space(conn)
    assert row["dim"] == 768 and int(row["active"]) == 1
    assert conn.query_one("SELECT COUNT(*) AS n FROM embedding_spaces WHERE code = ?", (_CODE,))["n"] == 1
