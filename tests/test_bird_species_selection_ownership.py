"""Species can classify via YOLO without owning an actively selected box (#593)."""

import json

import pytest

from modules import bird_species as bs
from modules import localization_selection as selections


class Connector:
    def __init__(self, selected):
        self.selected = selected
        self.calls = []
        self.writes = []

    def run_transaction(self, callback):
        return callback(self)

    def query_one(self, sql, params=None):
        self.calls.append(sql)
        if "FROM images" in sql:
            return {"id": 3, "folder_id": 8, "bird_bbox": {"selected": True}}
        return {"id": 1, "region_id": 9} if self.selected else None

    def execute(self, sql, params):
        self.writes.append(json.loads(params[0]))


@pytest.mark.parametrize("selected", [False, True])
def test_guard_locks_before_selection_check_and_invalidates_only_writes(monkeypatch, selected):
    conn = Connector(selected)
    invalidated = []
    monkeypatch.setattr(bs.db, "get_connector", lambda: conn)
    monkeypatch.setattr(bs.db, "invalidate_folder_phase_aggregates", lambda **kw: invalidated.append(kw))
    assert selections.write_legacy_bird_bbox(3, {"detected": False}) is (not selected)
    assert "FOR UPDATE" in conn.calls[0]
    assert "image_localization_selections" in conn.calls[1]
    assert conn.writes == ([] if selected else [{"detected": False}])
    assert invalidated == ([] if selected else [{"folder_id": 8}])


@pytest.mark.parametrize("regions", [False, True])
@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("path", ["success", "missing", "exception", "repair"])
def test_every_species_box_write_respects_selection(monkeypatch, tmp_path, regions, selected, path):
    conn = Connector(selected)
    direct_writes = []
    monkeypatch.setattr(bs.db, "get_connector", lambda: conn)
    monkeypatch.setattr(bs.db, "update_image_bird_bbox", lambda *a: direct_writes.append(a))
    monkeypatch.setattr(bs.db, "invalidate_folder_phase_aggregates", lambda **kw: None)
    monkeypatch.setattr(bs.db, "set_image_phase_status", lambda *a, **kw: None)
    monkeypatch.setattr(bs.db, "update_image_keywords_for_image", lambda *a, **kw: None)
    monkeypatch.setattr("modules.bird_species_eligibility.build_bird_species_keyword_csv", lambda *a, **kw: "birds")
    monkeypatch.setattr(bs, "use_regions_enabled", lambda: regions)
    # A geometry-selected small image still takes legacy inference.
    monkeypatch.setattr(bs, "species_input_for_image", lambda iid: {"mode": "legacy", "region": None})
    runner = bs.BirdSpeciesRunner()
    monkeypatch.setattr(runner, "_persist_bioclip_embedding", lambda iid: None)
    image = tmp_path / "bird.jpg"
    if path != "missing":
        image.write_bytes(b"image")

    class Classifier:
        last_bbox = {"detected": False}

        def classify(self, *a, **kw):
            if path == "exception":
                raise RuntimeError("classify failed")
            return [("Wren", 0.9)]

        def _ensure_detector(self):
            return object()

    runner.classifier = Classifier()
    row = {"id": 3, "file_path": str(image)}
    if path == "repair":
        monkeypatch.setattr("modules.remote_gpu.client.current_mode_or_none", lambda clf, *a: clf)
        monkeypatch.setattr(bs, "scan_bird_bbox_only", lambda *a: {"detected": False})
        runner._run_bbox_only_pass([row], job_id=None, log=lambda *a: None)
    else:
        runner._process_bird_species_image_row(row, species_list=["Wren"], threshold=0.5,
                                               top_k=1, phase_code="bird_species", log=lambda *a: None)
    assert direct_writes == []
    assert len(conn.writes) == (0 if selected else 1)


def test_guard_failure_suppresses_write_and_logs(monkeypatch, caplog):
    conn = Connector(False)

    def fail(callback):
        raise RuntimeError("database unavailable")

    conn.run_transaction = fail
    monkeypatch.setattr(bs.db, "get_connector", lambda: conn)
    assert selections.write_legacy_bird_bbox(3, {"detected": False}) is False
    assert conn.writes == []
    assert "database unavailable" in caplog.text
