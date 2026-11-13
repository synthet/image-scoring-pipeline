"""Regression tests for issue #861.

The index-only result that indexing passes for an image with no identity-hash row yet
(see ``tests/test_upsert_image_score_preservation.py``, issue #830) carries no title,
description or thumbnail. ``upsert_image`` defaulted those to ``""`` / ``None``, and the
``ON CONFLICT (file_path) DO UPDATE`` wrote them over the caption and description from the
keywords phase and over the stored thumbnail paths.
"""
import pytest

from modules import db_legacy as db
from tests.test_upsert_image_score_preservation import (
    _ScoredRowConnector,
    _images_upsert_params,
    _indexing_result,
)
from tests.test_upsert_image_score_preservation import upsert_env  # noqa: F401 (pytest fixture)

_STORED = {
    "title": "Heron on a post",
    "description": "A grey heron perched on a wooden post at dusk.",
    "thumbnail_path": "/thumbs/ab/abc123.jpg",
    "thumbnail_path_win": "D:\\thumbs\\ab\\abc123.jpg",
}


class _CaptionedRowConnector(_ScoredRowConnector):
    """The scored row at /photos/a.nef also carries a caption and thumbnails."""

    def query_one(self, sql, params=None):
        if "thumbnail_path" in sql and "FROM images WHERE id" in sql:
            return dict(_STORED)
        return super().query_one(sql, params)


@pytest.fixture
def connector(upsert_env, monkeypatch):  # noqa: F811 (requests the imported fixture)
    conn = _CaptionedRowConnector()
    monkeypatch.setattr(db, "get_connector", lambda: conn)
    return conn


def test_index_only_result_keeps_title_description_and_thumbnails(connector):
    db.upsert_image(1, _indexing_result())
    params = _images_upsert_params(connector.executed)
    for field, value in _STORED.items():
        assert value in params, f"an index-only result must not blank {field} (issue #861)"


def test_keywords_result_still_writes_title_and_description(connector):
    result = _indexing_result()
    result["title"] = "New caption"
    result["description"] = "New description"
    db.upsert_image(1, result)
    params = _images_upsert_params(connector.executed)
    assert "New caption" in params and "New description" in params
    assert _STORED["title"] not in params and _STORED["description"] not in params
    # Fields the result leaves out still keep their stored values.
    assert _STORED["thumbnail_path"] in params


def test_result_with_thumbnail_still_writes_it(connector):
    result = _indexing_result()
    result["thumbnail_path"] = "/thumbs/cd/new.jpg"
    db.upsert_image(1, result)
    params = _images_upsert_params(connector.executed)
    assert "/thumbs/cd/new.jpg" in params
    assert _STORED["thumbnail_path"] not in params
    assert _STORED["thumbnail_path_win"] not in params


def test_uuid_match_at_other_path_keeps_title_and_thumbnails(connector, monkeypatch):
    """A moved file matched by UUID updates the old row; an index-only result must not blank it."""
    monkeypatch.setattr(db, "find_image_id_by_uuid", lambda u: 99)

    class _MovedConnector(_CaptionedRowConnector):
        def query_one(self, sql, params=None):
            if "SELECT file_path, folder_id FROM images WHERE id" in sql:
                return {"file_path": "/old/a.nef", "folder_id": 3}
            return super().query_one(sql, params)

    moved = _MovedConnector()
    monkeypatch.setattr(db, "get_connector", lambda: moved)
    db.upsert_image(1, _indexing_result())
    for sql, params in moved.executed:
        if " ".join(sql.split()).startswith("UPDATE images SET job_id=?"):
            for value in _STORED.values():
                assert value in params
            return
    raise AssertionError("the UUID-match UPDATE was not executed")
