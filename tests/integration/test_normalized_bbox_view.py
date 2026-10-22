"""Migration 0043 upgrade, authority and rollback on an isolated PostgreSQL database."""
import importlib.util
from pathlib import Path
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from psycopg2.extras import Json
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from modules import db_postgres
from modules.test_db_constants import POSTGRES_TEST_DB

pytestmark = pytest.mark.postgres
BOX = dict(x1=10, y1=20, x2=60, y2=70, img_w=100, img_h=100, conf=0.8, area_frac=0.25)


@pytest.fixture
def view_database(monkeypatch):
    cfg = db_postgres.get_pg_config()
    assert cfg['dbname'] == POSTGRES_TEST_DB, 'only the isolated test database is permitted'
    url = URL.create('postgresql+psycopg2', username=cfg['user'], password=cfg['password'],
                     host=cfg['host'], port=cfg['port'], database=cfg['dbname'])
    engine = create_engine(url, poolclass=NullPool, connect_args={'connect_timeout': 5})
    path = Path(__file__).resolve().parents[2] / 'migrations/versions/0043_normalized_bird_bbox_compat_view.py'
    spec = importlib.util.spec_from_file_location('bbox_view_0043', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    try:
        with engine.connect() as bind:
            transaction = bind.begin()
            try:
                assert bind.exec_driver_sql('SELECT current_database()').scalar_one() == POSTGRES_TEST_DB
                schema = 'bbox_compat_' + uuid.uuid4().hex
                bind.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                bind.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                bind.exec_driver_sql("SET LOCAL statement_timeout='15s'")
                bind.exec_driver_sql('''
                    CREATE TABLE images(id integer PRIMARY KEY, bird_bbox jsonb);
                    CREATE TABLE image_localization_runs(
                        id integer PRIMARY KEY, image_id integer REFERENCES images,
                        detector_key text, is_current boolean, legacy_payload jsonb,
                        display_width integer, display_height integer);
                    CREATE UNIQUE INDEX current_run ON image_localization_runs(image_id,detector_key) WHERE is_current;
                    CREATE TABLE image_regions(
                        id integer PRIMARY KEY, localization_run_id integer REFERENCES image_localization_runs,
                        rank integer, x1 double precision, y1 double precision, x2 double precision, y2 double precision);
                    CREATE TABLE image_localization_selections(
                        id integer PRIMARY KEY, image_id integer REFERENCES images, detector_key text,
                        localization_run_id integer REFERENCES image_localization_runs,
                        region_id integer REFERENCES image_regions, projected_bird_bbox jsonb NOT NULL,
                        revoked_at timestamp);
                    CREATE UNIQUE INDEX active_selection ON image_localization_selections(image_id,detector_key)
                        WHERE revoked_at IS NULL;
                ''')
                bind.exec_driver_sql('INSERT INTO images VALUES (%s,%s)',
                                     [(i, Json(None if i == 4 else {'old': i})) for i in range(1, 12)])
                runs = [
                    (10, 1, 'bird', False, None, 100, 100), (11, 1, 'bird', True, None, 100, 100),
                    (20, 2, 'bird', True, Json({'detected': False}), None, None),
                    (30, 3, 'bird', True, None, 100, 100), (50, 5, 'bird', True, None, 100, 100),
                    (60, 6, 'bird', False, None, None, None),
                    (61, 6, 'bird', True, Json({'detected': False}), 100, 100),
                    (70, 7, 'bird', True, Json(None), None, None),
                    (80, 8, 'bird', True, Json({}), None, None),
                    (90, 9, 'bird', True, Json({'detected': False, 'error': 'decode_error'}), None, None),
                    (100, 10, 'coco', True, None, 100, 100),
                    (110, 11, 'bird', False, None, 100, 100), (111, 11, 'bird', True, None, 100, 100),
                ]
                bind.exec_driver_sql('INSERT INTO image_localization_runs VALUES (%s,%s,%s,%s,%s,%s,%s)', runs)
                bind.exec_driver_sql('INSERT INTO image_regions VALUES (%s,%s,%s,.1,.2,.6,.7)',
                                     [(100, 10, 2), (101, 11, 0), (500, 50, 0), (600, 60, 0),
                                      (1000, 100, 0), (1100, 111, 0)])
                bind.exec_driver_sql('INSERT INTO image_localization_selections VALUES (%s,%s,%s,%s,%s,%s,%s)', [
                    (1, 1, 'bird', 10, 100, Json(BOX), None),
                    (5, 5, 'bird', 50, 500, Json(BOX), '2026-01-01'),
                    (6, 6, 'bird', 60, 600, Json(BOX), None),
                    (10, 10, 'coco', 100, 1000, Json(BOX), None),
                    (11, 11, 'bird', 110, 1100, Json(BOX), None),
                ])
                monkeypatch.setattr(migration, 'op', Operations(MigrationContext.configure(bind)))
                yield bind, migration
            finally:
                # All schema, fixture and migration writes are uncommitted test work.
                transaction.rollback()
    finally:
        engine.dispose()


def values(bind):
    return dict(bind.exec_driver_sql('SELECT image_id,bird_bbox FROM image_bird_bbox_compat ORDER BY image_id').all())


def test_view_preserves_selected_imported_shadow_and_legacy_semantics(view_database):
    bind, migration = view_database
    before = bind.exec_driver_sql('SELECT id,bird_bbox FROM images ORDER BY id').all()
    migration.upgrade()
    assert values(bind) == {
        1: BOX, 2: {'detected': False}, 3: {'old': 3}, 4: None,
        5: {'old': 5}, 6: {'old': 6}, 7: {'old': 7}, 8: {},
        9: {'detected': False, 'error': 'decode_error'}, 10: {'old': 10}, 11: {'old': 11},
    }
    assert bind.exec_driver_sql('SELECT id,bird_bbox FROM images ORDER BY id').all() == before


def test_upgrade_is_repeatable_and_downgrade_preserves_rows(view_database):
    bind, migration = view_database
    before = bind.exec_driver_sql('SELECT id,bird_bbox FROM images ORDER BY id').all()
    migration.upgrade()
    expected = values(bind)
    migration.upgrade()
    assert values(bind) == expected
    migration.downgrade()
    assert bind.exec_driver_sql("SELECT to_regclass('image_bird_bbox_compat')").scalar_one() is None
    assert bind.exec_driver_sql('SELECT id,bird_bbox FROM images ORDER BY id').all() == before
    migration.upgrade()
    assert values(bind) == expected


def test_revocation_returns_to_legacy_without_detector_work(view_database):
    bind, migration = view_database
    migration.upgrade()
    assert values(bind)[1] == BOX
    bind.exec_driver_sql('UPDATE image_localization_selections SET revoked_at=CURRENT_TIMESTAMP WHERE id=1')
    assert values(bind)[1] == {'old': 1}
