"""Capture key format and tombstone matching (no database required)."""

import datetime
import importlib.util
import json
from pathlib import Path

import pytest

from modules import db_legacy
from modules.capture_key import capture_key, capture_key_from_exif

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "tests" / "fixtures" / "capture_key_vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_shared_vectors(vector):
    assert capture_key(vector["model"], vector["shutter_count"], vector["date_time_original"]) == vector["expected"]


def test_accepts_a_datetime():
    when = datetime.datetime(2026, 1, 19, 14, 56, 4, 520000)
    assert capture_key("NIKON Z 8", 12345, when) == "NIKON Z 8|12345|2026-01-19T14:56:04"


def test_from_extract_exif_output():
    exif = {"model": "NIKON Z 8", "shutter_count": 12345, "date_time_original": "2026:01:19 14:56:04"}
    assert capture_key_from_exif(exif) == "NIKON Z 8|12345|2026-01-19T14:56:04"


@pytest.mark.parametrize("exif", [None, {}, {"model": "NIKON Z 8"}])
def test_from_exif_without_the_fields(exif):
    assert capture_key_from_exif(exif) is None


class _Connector:
    """Answers tombstone lookups from a set of (column, value) pairs."""

    def __init__(self, rows=(), fail_on=None):
        self.rows = set(rows)
        self.fail_on = fail_on
        self.queries = []

    def query_one(self, sql, params):
        self.queries.append(sql)
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("column does not exist")
        for column, value in self.rows:
            if f"WHERE {column} = ?" in sql and params[0] == value:
                return {"x": 1}
        return None


def test_blocklist_matches_capture_key_at_a_new_path(monkeypatch):
    key = "NIKON Z 8|12345|2026-01-19T14:56:04"
    monkeypatch.setattr(db_legacy, "get_connector", lambda: _Connector({("capture_key", key)}))
    assert db_legacy.is_image_in_deleted_blocklist("/new/root/DSC_1.NEF", "DSC_1.NEF", capture_key=key)


def test_blocklist_ignores_a_different_capture_key(monkeypatch):
    stored = "NIKON Z 8|12345|2026-01-19T14:56:04"
    monkeypatch.setattr(db_legacy, "get_connector", lambda: _Connector({("capture_key", stored)}))
    other = "NIKON Z 8|12346|2026-01-19T14:56:04"
    assert not db_legacy.is_image_in_deleted_blocklist("/new/root/DSC_2.NEF", "DSC_2.NEF", capture_key=other)


def test_blocklist_without_a_key_does_not_query_it(monkeypatch):
    connector = _Connector()
    monkeypatch.setattr(db_legacy, "get_connector", lambda: connector)
    assert not db_legacy.is_image_in_deleted_blocklist("/new/root/DSC_1.NEF", "DSC_1.NEF")
    assert not any("capture_key" in q for q in connector.queries)


def test_path_route_still_works_if_the_column_is_missing(monkeypatch):
    """A database not yet migrated must keep its existing protection."""
    connector = _Connector({("original_path", "/lib/DSC_1.NEF")}, fail_on="capture_key")
    monkeypatch.setattr(db_legacy, "get_connector", lambda: connector)
    assert db_legacy.is_image_in_deleted_blocklist("/lib/DSC_1.NEF", "DSC_1.NEF", capture_key="k")


def _migration():
    path = ROOT / "migrations" / "versions" / "0049_tombstone_capture_key.py"
    spec = importlib.util.spec_from_file_location("migration_0049", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chain():
    migration = _migration()
    assert migration.revision == "0049"
    assert migration.down_revision == "0048"


def test_migration_avoids_sqlalchemy_text_binds():
    """HH24:MI:SS would be read as bind parameters by op.execute."""
    text = (ROOT / "migrations" / "versions" / "0049_tombstone_capture_key.py").read_text(encoding="utf-8")
    assert "exec_driver_sql" in text
    assert "op.execute(" not in text
