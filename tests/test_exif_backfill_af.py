"""Unit tests for backfill_af_metadata (#726): re-extract AF geometry for rows cached before migration 0044."""

from __future__ import annotations

import pytest

from modules import db, exif_extractor, utils


class FakeConnector:
    def __init__(self, rows):
        self.rows = rows
        self.calls: list[tuple[str, tuple]] = []

    def query(self, sql, params=None):
        self.calls.append((sql, tuple(params or ())))
        return list(self.rows)


@pytest.fixture
def harness(monkeypatch):
    state = {"exif": {}, "fresh": {}, "missing": set(), "upserts": []}

    def fake_extract(path, image_id=None):
        return state["fresh"].get(image_id)

    def fake_upsert(image_id, data):
        state["upserts"].append((image_id, data))
        return True

    monkeypatch.setattr(exif_extractor, "extract_exif", fake_extract)
    monkeypatch.setattr(db, "get_image_exif", lambda image_id: state["exif"].get(image_id, {}))
    monkeypatch.setattr(db, "upsert_image_exif", fake_upsert)
    monkeypatch.setattr(utils, "resolve_file_path", lambda file_path, image_id=None: file_path)
    monkeypatch.setattr(
        exif_extractor.os.path, "exists", lambda p: not any(p.endswith(m) for m in state["missing"])
    )
    return state


def _use_rows(monkeypatch, rows):
    conn = FakeConnector(rows)
    monkeypatch.setattr(db, "get_connector", lambda: conn)
    return conn


AF = {"box": {"left": 0.4, "top": 0.3, "width": 0.05, "height": 0.05}, "mode": "Wide (L)", "version": "0400"}


def test_selects_only_null_af_rows_for_model_pattern_in_id_order(monkeypatch, harness):
    conn = _use_rows(monkeypatch, [])
    exif_extractor.backfill_af_metadata(limit=50, after_id=1000, model_like="NIKON Z%", path_like="%/2026-10-24/%")
    sql, params = conn.calls[0]
    assert "ex.af_metadata IS NULL" in sql
    assert "ex.model LIKE ?" in sql
    assert "i.file_path LIKE ?" in sql
    assert "i.id > ?" in sql
    assert "ORDER BY i.id" in sql
    assert "LIMIT 50" in sql
    assert params == (1000, "NIKON Z%", "%/2026-10-24/%")


def test_updates_rows_and_counts_outcomes(monkeypatch, harness):
    _use_rows(monkeypatch, [
        {"image_id": 1, "file_path": "/mnt/d/a.nef"},
        {"image_id": 2, "file_path": "/mnt/d/b.nef"},
        {"image_id": 3, "file_path": "/mnt/d/gone.nef"},
        {"image_id": 4, "file_path": "/mnt/d/unreadable.nef"},
    ])
    harness["exif"] = {1: {"model": "NIKON Z 8", "iso": 400}, 2: {"model": "NIKON Z 8"}}
    harness["fresh"] = {
        1: {"model": "NIKON Z 8", "af_metadata": AF},
        2: {"model": "NIKON Z 8", "af_metadata": None},  # AFCoordinatesAvailable = 0
    }
    harness["missing"] = {"gone.nef"}

    stats = exif_extractor.backfill_af_metadata()

    assert stats == {
        "checked": 4,
        "updated": 1,
        "no_af": 1,
        "skipped_no_file": 1,
        "skipped_no_exif": 1,
        "errors": 0,
        "last_id": 4,
    }
    written = dict(harness["upserts"])
    assert written[1]["af_metadata"] == AF
    assert written[1]["iso"] == 400, "merge keeps unrelated cached columns"
    assert 2 in written, "a checked row is still re-cached (refreshes extracted_at)"


def test_empty_batch_reports_last_id_unchanged(monkeypatch, harness):
    _use_rows(monkeypatch, [])
    stats = exif_extractor.backfill_af_metadata(after_id=77)
    assert stats["checked"] == 0
    assert stats["last_id"] == 77


def test_upsert_failure_counts_as_error(monkeypatch, harness):
    _use_rows(monkeypatch, [{"image_id": 9, "file_path": "/mnt/d/x.nef"}])
    harness["fresh"] = {9: {"model": "NIKON Z 8", "af_metadata": AF}}
    monkeypatch.setattr(db, "upsert_image_exif", lambda image_id, data: False)
    stats = exif_extractor.backfill_af_metadata()
    assert stats["errors"] == 1
    assert stats["updated"] == 0
    assert stats["last_id"] == 9


def test_exiftool_supports_af_requires_13(monkeypatch):
    monkeypatch.setattr(exif_extractor, "get_exiftool_version", lambda: "12.40")
    assert exif_extractor.exiftool_supports_af() is False
    monkeypatch.setattr(exif_extractor, "get_exiftool_version", lambda: "13.52")
    assert exif_extractor.exiftool_supports_af() is True
    monkeypatch.setattr(exif_extractor, "get_exiftool_version", lambda: None)
    assert exif_extractor.exiftool_supports_af() is False
