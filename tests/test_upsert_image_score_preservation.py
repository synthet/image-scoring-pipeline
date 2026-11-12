"""Regression tests for issue #830.

Indexing registers an image that has no identity-hash row yet by calling ``upsert_image``
with an index-only result: path, hash, folder and metadata, but no scores. ``upsert_image``
wrote ``score``, the composites, ``rating`` and ``label`` unconditionally, and the
``ON CONFLICT (file_path) DO UPDATE`` set every column from that result. So re-indexing an
already-scored image (auto-drive heals "done but no identity hash" and re-runs indexing)
reset ``score_general`` to NULL, ``rating`` to 0 and ``label`` to ''. The per-model rows
survived, which is why ``finalize_phantom_scores`` could rebuild the composites later.
"""
import pytest

from modules import db_legacy as db
from tests.test_upsert_image_keyword_preservation import _FakeConnector

_PREVIOUS = {
    "score": 0.71,
    "score_technical": 0.64,
    "score_aesthetic": 0.58,
    "score_general": 0.71,
    "model_version": "2.5.0",
    "rating": 4,
    "label": "Green",
}


class _ScoredRowConnector(_FakeConnector):
    """The image at /photos/a.nef already carries a composite, rating and label."""

    def query_one(self, sql, params=None):
        if "score_general" in sql and "FROM images WHERE id" in sql:
            return dict(_PREVIOUS)
        return super().query_one(sql, params)


@pytest.fixture
def upsert_env(monkeypatch):
    """Stub out everything upsert_image touches except the score columns."""
    connector = _ScoredRowConnector()
    monkeypatch.setattr(db, "get_connector", lambda: connector)
    monkeypatch.setattr(db, "generate_image_uuid", lambda meta: "uuid-fixed")
    monkeypatch.setattr(db, "find_image_id_by_uuid", lambda u: 42)
    monkeypatch.setattr(db, "get_or_create_folder", lambda p: 7)
    monkeypatch.setattr(db, "_validate_folder_id_or_from_path", lambda fid, p: fid)
    monkeypatch.setattr(db, "_write_legacy_keywords_column", lambda: False)
    monkeypatch.setattr(db, "_write_legacy_scores_json_column", lambda: False)
    monkeypatch.setattr(db, "_scores_json_column_value", lambda r: None)
    for name in (
        "_sync_image_keywords", "_write_image_model_scores", "_write_image_technical_failures",
        "register_image_path", "invalidate_folder_images_cache",
        "invalidate_folder_phase_aggregates", "resolve_windows_path",
    ):
        monkeypatch.setattr(db, name, lambda *a, **k: None)
    monkeypatch.setattr(db.event_manager, "broadcast_threadsafe", lambda *a, **k: None)
    return {"connector": connector}


def _indexing_result():
    """What ``indexing_runner`` passes for an image with no identity-hash row yet."""
    return {
        "image_path": "/photos/a.nef",
        "image_hash": "abc123",
        "hash_version": 2,
        "folder_id": 7,
        "metadata": {"exif": {}},
    }


def _images_upsert_params(executed):
    for sql, params in executed:
        if "INTO images" in " ".join(sql.split()) and "score_general" in sql:
            return params
    raise AssertionError("no images upsert was executed")


def _score_fields(params):
    # _upsert_head: job_id, file_path, file_name, file_type, score,
    # score_technical, score_aesthetic, score_general, model_version, rating, label
    keys = ("score", "score_technical", "score_aesthetic", "score_general",
            "model_version", "rating", "label")
    return dict(zip(keys, params[4:11]))


def test_index_only_result_keeps_existing_scores(upsert_env):
    db.upsert_image(1, _indexing_result())
    params = _images_upsert_params(upsert_env["connector"].executed)
    assert _score_fields(params) == _PREVIOUS, (
        "an index-only result must not reset score_general, rating or label (issue #830)"
    )


def test_index_only_result_still_writes_identity_hash(upsert_env):
    db.upsert_image(1, _indexing_result())
    params = _images_upsert_params(upsert_env["connector"].executed)
    assert "abc123" in params and 2 in params


def test_scoring_result_still_overwrites_scores(upsert_env):
    result = _indexing_result()
    result["summary"] = {"weighted_scores": {"technical": 0.5, "aesthetic": 0.4, "general": 0.45}}
    result["nef_metadata"] = {"rating": 2, "label": "Red"}
    db.upsert_image(1, result)
    fields = _score_fields(_images_upsert_params(upsert_env["connector"].executed))
    assert fields["score_general"] == 0.45
    assert fields["rating"] == 2 and fields["label"] == "Red"


def test_uuid_match_at_other_path_keeps_existing_scores(upsert_env, monkeypatch):
    """A moved file matched by UUID updates the old row; an index-only result must not blank it."""
    monkeypatch.setattr(db, "find_image_id_by_uuid", lambda u: 99)

    class _MovedConnector(_ScoredRowConnector):
        def query_one(self, sql, params=None):
            if "SELECT file_path, folder_id FROM images WHERE id" in sql:
                return {"file_path": "/old/a.nef", "folder_id": 3}
            return super().query_one(sql, params)

    connector = _MovedConnector()
    monkeypatch.setattr(db, "get_connector", lambda: connector)
    db.upsert_image(1, _indexing_result())
    for sql, params in connector.executed:
        if " ".join(sql.split()).startswith("UPDATE images SET job_id=?"):
            # dup_core: job_id, file_path, file_name, file_type, score,
            # score_technical, score_aesthetic, score_general, model_version, rating, label
            assert _score_fields(params) == _PREVIOUS
            return
    raise AssertionError("the UUID-match UPDATE was not executed")
