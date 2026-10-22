"""A legacy backfill must not overwrite a selection promoted during detection."""
import json

import pytest

from modules import db
from scripts.backfill_bird_bbox import apply_detection_result, fetch_candidates


SELECTED = {"x1": 20, "y1": 20, "x2": 60, "y2": 60,
            "img_w": 100, "img_h": 100, "conf": 0.8, "area_frac": 0.16}
DETECTED = {"x1": 1, "y1": 1, "x2": 99, "y2": 99,
            "img_w": 100, "img_h": 100, "conf": 0.9, "area_frac": 0.9604}


class MemoryDatabase:
    def __init__(self):
        self.bbox = None
        self.selected = False
        self.transaction = False
        self.image_exists = True
        self.writes = []
        self.query_log = []

    def cursor(self):
        return self

    def execute(self, sql, params):
        self.query_log.append(sql)
        if sql.lstrip().startswith("UPDATE images"):
            self.bbox = json.loads(params[0]) if params[0] is not None else None
            self.writes.append(self.bbox)

    def fetchall(self):
        assert "i.bird_bbox IS NULL" in self.query_log[-1]
        return [] if self.bbox is not None else [{"id": 3, "file_path": "unused",
                                                  "thumbnail_path": None, "thumbnail_path_win": None}]

    def close(self):
        pass

    def run_transaction(self, callback):
        self.transaction = True
        try:
            return callback(self)
        finally:
            self.transaction = False

    def query_one(self, sql, params):
        self.query_log.append(sql)
        if "image_localization_selections" in sql:
            assert self.transaction and any("FOR UPDATE" in item for item in self.query_log)
            return {"id": 4, "region_id": 9} if self.selected else None
        return {"folder_id": 8} if self.image_exists else None


def test_backfill_preserves_selection_created_after_candidate_fetch(monkeypatch):
    memory = MemoryDatabase()
    invalidations = []
    monkeypatch.setattr(db, "get_db", lambda: memory)
    monkeypatch.setattr(db, "get_connector", lambda: memory)
    monkeypatch.setattr(db, "invalidate_folder_phase_aggregates", lambda **kw: invalidations.append(kw))
    candidates = fetch_candidates(all_null=True, limit=1)
    assert [row["id"] for row in candidates] == [3]

    memory.selected = True
    memory.bbox = dict(SELECTED)
    outcome = apply_detection_result(candidates[0]["id"], DETECTED, dry_run=False)

    assert memory.bbox == SELECTED
    assert memory.writes == []
    assert invalidations == []
    assert outcome == "write_error"


@pytest.mark.parametrize("bbox", [DETECTED, None])
def test_unselected_write_and_clear_invalidate_rollup(monkeypatch, bbox):
    memory = MemoryDatabase()
    invalidations = []
    monkeypatch.setattr(db, "get_connector", lambda: memory)
    monkeypatch.setattr(db, "invalidate_folder_phase_aggregates", lambda **kw: invalidations.append(kw))
    assert db.update_image_bird_bbox(3, bbox) is True
    assert memory.bbox == bbox
    assert memory.writes == [bbox]
    assert invalidations == [{"folder_id": 8}]


def test_missing_image_is_not_reported_as_written(monkeypatch):
    memory = MemoryDatabase()
    memory.image_exists = False
    monkeypatch.setattr(db, "get_connector", lambda: memory)
    assert db.update_image_bird_bbox(3, DETECTED) is False
    assert memory.writes == []


def test_failed_transaction_suppresses_write(monkeypatch):
    memory = MemoryDatabase()

    def fail(callback):
        raise RuntimeError("synthetic unavailable transaction")

    memory.run_transaction = fail
    monkeypatch.setattr(db, "get_connector", lambda: memory)
    assert db.update_image_bird_bbox(3, DETECTED) is False
    assert memory.writes == []
