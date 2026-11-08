"""capture_key on deleted_images, against the isolated PostgreSQL test catalog."""

import importlib.util
import json
import uuid
from pathlib import Path

import psycopg2
import pytest

from modules import db_postgres
from modules.capture_key import capture_key
from scripts.neardupe_maintenance.postgres_adapter import PostgresAdapter

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "tests" / "fixtures" / "capture_key_vectors.json").read_text(encoding="utf-8"))
KEY = "NIKON Z 8|12345|2026-01-19T14:56:04"


@pytest.fixture
def conn(clean_postgres):
    connection = psycopg2.connect(**db_postgres.get_pg_config())
    with connection.cursor() as c:
        c.execute("SELECT current_database()")
        assert c.fetchone()[0] == clean_postgres_name()
    connection.rollback()
    yield connection
    connection.rollback()
    with connection.cursor() as c:
        c.execute("SELECT pg_advisory_unlock_all()")
    connection.commit()
    connection.close()


def clean_postgres_name():
    from modules.test_db_constants import POSTGRES_TEST_DB

    return POSTGRES_TEST_DB


def _image(c, name, *, stack=None, exif=True):
    path = f"/tmp/capture-key-{uuid.uuid4().hex}/{name}"
    c.execute(
        "INSERT INTO images(file_path,file_name,image_uuid,stack_id) VALUES (%s,%s,%s,%s) RETURNING id",
        (path, name, str(uuid.uuid4()), stack),
    )
    image_id = c.fetchone()[0]
    if exif:
        c.execute(
            "INSERT INTO image_exif(image_id,model,shutter_count,date_time_original) VALUES (%s,%s,%s,%s)",
            (image_id, "NIKON Z 8", 12345, "2026-01-19 14:56:04.52"),
        )
    return image_id, path


def _keys(c, image_id):
    c.execute("SELECT capture_key FROM deleted_images WHERE original_id=%s ORDER BY id", (image_id,))
    return [r[0] for r in c.fetchall()]


def test_trigger_records_the_key_before_image_exif_cascades(conn):
    with conn.cursor() as c:
        image_id, _ = _image(c, "a.NEF")
        c.execute("DELETE FROM images WHERE id=%s", (image_id,))
        assert _keys(c, image_id) == [KEY]
        c.execute("SELECT count(*) FROM image_exif WHERE image_id=%s", (image_id,))
        assert c.fetchone()[0] == 0
    conn.commit()


def test_trigger_writes_null_without_exif(conn):
    with conn.cursor() as c:
        image_id, _ = _image(c, "b.NEF", exif=False)
        c.execute("DELETE FROM images WHERE id=%s", (image_id,))
        assert _keys(c, image_id) == [None]
    conn.commit()


@pytest.mark.parametrize(
    "vector",
    [v for v in VECTORS if v["expected"]],
    ids=lambda v: v["name"],
)
def test_sql_key_equals_python_key(conn, vector):
    """The catalog stores a timestamp and an integer, so only well-formed vectors apply."""
    stored = vector["expected"].rsplit("|", 1)[1].replace("T", " ")
    with conn.cursor() as c:
        image_id, _ = _image(c, "v.NEF", exif=False)
        c.execute(
            "INSERT INTO image_exif(image_id,model,shutter_count,date_time_original) VALUES (%s,%s,%s,%s)",
            (image_id, vector["model"], int(vector["shutter_count"]), stored),
        )
        c.execute("SELECT image_capture_key(%s)", (image_id,))
        assert c.fetchone()[0] == vector["expected"]
        assert vector["expected"] == capture_key(vector["model"], vector["shutter_count"], stored)
    conn.rollback()


@pytest.mark.parametrize(
    "columns",
    [("NIKON Z 8", None, "2026-01-19 14:56:04"), ("NIKON Z 8", 0, "2026-01-19 14:56:04"),
     ("NIKON Z 8", 12345, None), (None, 12345, "2026-01-19 14:56:04"), ("  ", 12345, "2026-01-19 14:56:04")],
)
def test_sql_key_is_null_when_a_field_is_missing(conn, columns):
    with conn.cursor() as c:
        image_id, _ = _image(c, "n.NEF", exif=False)
        c.execute(
            "INSERT INTO image_exif(image_id,model,shutter_count,date_time_original) VALUES (%s,%s,%s,%s)",
            (image_id, *columns),
        )
        c.execute("SELECT image_capture_key(%s)", (image_id,))
        assert c.fetchone()[0] is None
    conn.rollback()


def test_adapter_keeps_the_key_although_it_deletes_image_exif_first(conn):
    """direct_tables removes image_exif before images, so the trigger's own row has no key."""
    with conn.cursor() as c:
        c.execute("INSERT INTO stacks(name) VALUES (%s) RETURNING id", ("capture-key-test",))
        stack = c.fetchone()[0]
        removed, removed_path = _image(c, "1.NEF", stack=stack)
        keeper, keeper_path = _image(c, "2.NEF", stack=stack, exif=False)
        c.execute("SELECT image_uuid FROM images WHERE id=%s", (removed,))
        image_uuid = c.fetchone()[0]
    conn.commit()
    row = {"image_id": removed, "db_path": removed_path, "image_uuid": image_uuid,
           "replacement_id": keeper, "replacement_db_path": keeper_path}
    adapter = PostgresAdapter(conn)
    adapter.begin_batch(row)
    snapshot = adapter.snapshot(row)
    adapter.delete(row)
    with conn.cursor() as c:
        assert KEY in _keys(c, removed)
    conn.rollback()
    adapter.restore(row, snapshot)
    with conn.cursor() as c:
        assert _keys(c, removed) == []
    conn.rollback()


def _migration():
    path = ROOT / "migrations" / "versions" / "0049_tombstone_capture_key.py"
    spec = importlib.util.spec_from_file_location("migration_0049", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_is_idempotent_on_a_current_schema(conn):
    migration = _migration()
    with conn.cursor() as c:
        for statement in migration.UPGRADE_SQL:
            c.execute(statement)
        image_id, _ = _image(c, "m.NEF")
        c.execute("DELETE FROM images WHERE id=%s", (image_id,))
        assert _keys(c, image_id) == [KEY]
    conn.rollback()


def test_migration_downgrade_then_upgrade(conn):
    migration = _migration()
    with conn.cursor() as c:
        for statement in migration.DOWNGRADE_SQL:
            c.execute(statement)
        c.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name='deleted_images' AND column_name='capture_key'"
        )
        assert c.fetchone()[0] == 0
        image_id, _ = _image(c, "d.NEF")
        c.execute("DELETE FROM images WHERE id=%s", (image_id,))
        for statement in migration.UPGRADE_SQL:
            c.execute(statement)
        assert _keys(c, image_id) == [None]
    conn.rollback()
