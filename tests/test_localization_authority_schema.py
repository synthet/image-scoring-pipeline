"""Authority bootstrap and immutable forward migration must share a contract."""
from types import SimpleNamespace
import importlib.util
from pathlib import Path

from modules.db_schema import initialize_schema


TABLES = (
    "localization_authority_scan_faults",
    "localization_authority_control", "localization_authority_policies",
    "localization_authority_observations", "localization_authority_reservations",
    "localization_authority_evaluations", "localization_authority_attempts",
    "localization_authority_lineage",
)


def test_bootstrap_installs_dormant_authority_tables():
    statements = []
    cursor = SimpleNamespace(execute=lambda sql, *args: statements.append(sql), fetchone=lambda: None)
    connection = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    initialize_schema(cursor, conn=connection, default_embedding_space_sql="SELECT 1",
                      extra_embedding_spaces_sql=())
    sql = "\n".join(statements)
    for table in TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql


def test_migration_matches_bootstrap_and_cleanup():
    from modules.db_schema.authority import AUTHORITY_SCHEMA_SQL
    from modules.db_postgres import POSTGRES_APP_TABLES

    path = Path(__file__).resolve().parents[1] / "migrations/versions/0045_localization_authority.py"
    spec = importlib.util.spec_from_file_location("authority_0045", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "0045" and migration.down_revision == "0044"
    assert migration.AUTHORITY_SCHEMA_SQL == AUTHORITY_SCHEMA_SQL
    assert set(TABLES) <= set(POSTGRES_APP_TABLES)
