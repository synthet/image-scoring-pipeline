"""Regression tests for issue #347.

``upsert_image`` used to call ``_sync_image_keywords`` unconditionally with the
CSV derived from ``result.get("keywords", [])``.  A scoring-only result carries
no ``keywords`` key, so the CSV was empty and ``_sync_image_keywords`` deleted
every ``image_keywords`` row for the image and committed.  Re-scoring an already
tagged image therefore destroyed its keywords (and, because the bird_species
phase scopes work by the normalized ``birds`` keyword, silently took the image
out of species scope).
"""
import pytest

from modules import db_legacy as db


class _FakeTx:
    def __init__(self, executed):
        self.executed = executed

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def execute_returning(self, sql, params=None):
        self.executed.append((sql, params))
        return [{"id": 42}]

    def query_one(self, sql, params=None):
        return None


class _FakeConnector:
    """Minimal connector: records writes, answers the lookups upsert_image makes."""

    def __init__(self):
        self.executed = []

    def query_one(self, sql, params=None):
        if "FROM images WHERE file_path" in sql:
            return {"id": 42, "folder_id": 7}
        if "FROM images WHERE id" in sql:
            return {"file_path": "/photos/a.nef", "folder_id": 7}
        return None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def run_transaction(self, callback):
        return callback(_FakeTx(self.executed))


@pytest.fixture
def upsert_env(monkeypatch):
    """Stub out everything upsert_image touches except the keyword logic."""
    calls = {"sync": [], "connector": _FakeConnector()}

    monkeypatch.setattr(db, "get_connector", lambda: calls["connector"])
    monkeypatch.setattr(db, "generate_image_uuid", lambda meta: "uuid-fixed")
    monkeypatch.setattr(db, "find_image_id_by_uuid", lambda u: 42)
    monkeypatch.setattr(db, "get_or_create_folder", lambda p: 7)
    monkeypatch.setattr(db, "_validate_folder_id_or_from_path", lambda fid, p: fid)
    monkeypatch.setattr(db, "_write_legacy_keywords_column", lambda: True)
    monkeypatch.setattr(db, "_write_legacy_scores_json_column", lambda: False)
    monkeypatch.setattr(db, "_scores_json_column_value", lambda r: None)
    monkeypatch.setattr(
        db, "_sync_image_keywords",
        lambda image_id, kw, **kw2: calls["sync"].append((image_id, kw)),
    )
    for name in (
        "_write_image_model_scores", "_write_image_technical_failures",
        "register_image_path", "invalidate_folder_images_cache",
        "invalidate_folder_phase_aggregates",
    ):
        monkeypatch.setattr(db, name, lambda *a, **k: None)
    monkeypatch.setattr(db, "resolve_windows_path", lambda *a, **k: None)
    monkeypatch.setattr(db.event_manager, "broadcast_threadsafe", lambda *a, **k: None)
    return calls


def _scoring_result():
    """A scoring-phase result: scores, no 'keywords' key."""
    return {
        "image_path": "/photos/a.nef",
        "image_name": "a.nef",
        "score": 0.8,
        "metadata": {"exif": {}},
    }


def _wrote_legacy_keywords_column(executed):
    """True when any statement wrote the legacy images.keywords column."""
    for sql, _params in executed:
        norm = " ".join(sql.split())
        if "UPDATE images SET" in norm and "keywords=?" in norm:
            return True
        if "UPDATE OR INSERT INTO images" in norm and "keywords, title" in norm:
            return True
    return False


def test_scoring_result_without_keywords_does_not_touch_normalized(upsert_env):
    db.upsert_image(1, _scoring_result())
    assert upsert_env["sync"] == [], (
        "scoring-only result must not sync keywords; syncing an empty CSV "
        "deletes every image_keywords row (issue #347)"
    )


def test_scoring_result_without_keywords_does_not_blank_legacy_column(upsert_env):
    db.upsert_image(1, _scoring_result())
    assert not _wrote_legacy_keywords_column(upsert_env["connector"].executed), (
        "scoring-only result must not write the legacy keywords column"
    )


def test_tagging_result_with_keywords_still_syncs(upsert_env):
    result = _scoring_result()
    result["keywords"] = ["wildlife", "birds"]
    db.upsert_image(1, result)
    assert upsert_env["sync"] == [(42, "wildlife,birds")]


def test_explicit_empty_keyword_list_still_clears(upsert_env):
    """An explicit empty list means 'tagging found nothing' — clearing is correct."""
    result = _scoring_result()
    result["keywords"] = []
    db.upsert_image(1, result)
    assert upsert_env["sync"] == [(42, "")]
