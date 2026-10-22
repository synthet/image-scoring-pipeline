"""Fresh database bootstrap must install the SQL compatibility contract."""
from types import SimpleNamespace
import importlib.util
from pathlib import Path

from modules.db_schema.review import BIRD_BBOX_COMPAT_VIEW_SQL, initialize_review_schema


def test_bootstrap_registers_normalized_bird_bbox_compatibility_view():
    statements = []
    cursor = SimpleNamespace(execute=lambda sql, *params: statements.append(sql))
    connection = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    initialize_review_schema(cursor, conn=connection)
    views = [sql for sql in statements if 'CREATE OR REPLACE VIEW image_bird_bbox_compat' in sql]
    assert len(views) == 1
    assert 'image_localization_selections' in views[0]
    assert 'projected_bird_bbox' in views[0]


def test_migration_preserves_the_bootstrap_view_contract():
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/0043_normalized_bird_bbox_compat_view.py'
    spec = importlib.util.spec_from_file_location('bbox_compat_0043', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == '0043' and migration.down_revision == '0042'
    assert migration._CREATE_VIEW_SQL.strip() == BIRD_BBOX_COMPAT_VIEW_SQL.strip()
