"""Migration 0047 (localization species, #731): literal ``%`` must survive the DB-API call."""

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0047_localization_species.py"


def _load_0047():
    spec = importlib.util.spec_from_file_location("migration_0047", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_upgrade_sql_survives_driver_percent_formatting(monkeypatch):
    mod = _load_0047()
    sent = []

    class Bind:
        def exec_driver_sql(self, sql, *args):
            sent.append(sql)

    monkeypatch.setattr(mod.op, "get_bind", lambda: Bind())
    mod.upgrade()

    assert "%" in mod.SPECIES_SCHEMA_SQL  # LIKE '%birds%'
    # exec_driver_sql hands psycopg2 an empty mapping, so it %-formats the statement.
    assert sent[0] % {} == mod.SPECIES_SCHEMA_SQL


@pytest.mark.postgres
def test_upgrade_0047_runs_on_bootstrapped_schema(postgres_test_session, clean_postgres):
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.stamp(cfg, "0046")
    command.upgrade(cfg, "0047")  # idempotent over init_db(); failed with TypeError before #731
