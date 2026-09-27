"""Stage 5 slice 1 (#444): bird_species consumes the current localization region."""

from PIL import Image

import modules.bird_species as bs
from modules.bird_species import BirdSpeciesRunner, species_input_for_image


class _Conn:
    def __init__(self, row=None, exc=None):
        self.row, self.exc = row, exc

    def query_one(self, sql, params):
        if self.exc:
            raise self.exc
        return self.row


def _with_conn(monkeypatch, conn):
    monkeypatch.setattr(bs.db, "get_connector", lambda: conn)


def test_detected_run_selects_region(monkeypatch):
    _with_conn(monkeypatch, _Conn({"run_id": 7, "status": "detected", "region_id": 9,
                                    "x1": 0.1, "y1": 0.2, "x2": 0.5, "y2": 0.6}))
    choice = species_input_for_image(1)
    assert choice["mode"] == "region" and choice["region"] == (0.1, 0.2, 0.5, 0.6)
    assert choice["region_id"] == 9


def test_no_detection_run_selects_full_frame(monkeypatch):
    _with_conn(monkeypatch, _Conn({"run_id": 7, "status": "no_detection", "region_id": None}))
    assert species_input_for_image(1)["mode"] == "full_frame"


def test_missing_error_or_failed_lookup_falls_back_to_legacy(monkeypatch):
    for conn in (_Conn(None), _Conn({"run_id": 7, "status": "retryable_error", "region_id": None}),
                 _Conn({"run_id": 7, "status": "detected", "region_id": None}),
                 _Conn(exc=RuntimeError("db down"))):
        _with_conn(monkeypatch, conn)
        assert species_input_for_image(1)["mode"] == "legacy"


def test_crop_region_uses_detector_padding():
    clf = bs.BioCLIPClassifier.__new__(bs.BioCLIPClassifier)
    clf._region_cropper = None
    crop = clf._crop_region(Image.new("RGB", (1000, 500)), (0.2, 0.2, 0.6, 0.6))
    # 400x200 px box, default padding 0.10 -> 40 / 20 px each side.
    assert crop.size == (480, 240)


class _FakeClassifier:
    def __init__(self, last_bbox=None):
        self.calls = []
        self.last_bbox = last_bbox

    def classify(self, path, species, threshold, top_k, region=None, use_detector=True):
        self.calls.append({"region": region, "use_detector": use_detector})
        return [("Carolina Wren", 0.9)]


def _run_row(monkeypatch, tmp_path, *, use_regions, choice, legacy_bbox=None, projection=None):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    writes = {"bbox": [], "sources": []}
    runner = BirdSpeciesRunner()
    runner.classifier = _FakeClassifier(last_bbox=legacy_bbox)
    monkeypatch.setattr(bs, "use_regions_enabled", lambda: use_regions)
    monkeypatch.setattr(bs, "species_input_for_image", lambda image_id: choice)
    monkeypatch.setattr(runner, "_persist_bioclip_embedding", lambda image_id: None)
    monkeypatch.setattr(bs.db, "update_image_bird_bbox", lambda i, b: writes["bbox"].append((i, b)))
    monkeypatch.setattr(bs.db, "set_image_phase_status", lambda *a, **kw: None)
    monkeypatch.setattr(bs.db, "get_connector", lambda: object())
    monkeypatch.setattr("modules.localization_legacy.read_bird_bbox",
                        lambda conn, image_id, prefer_normalized=None: projection)
    monkeypatch.setattr("modules.bird_species_eligibility.build_bird_species_keyword_csv",
                        lambda image_id, legacy_csv, new_species: ",".join(new_species))
    monkeypatch.setattr(bs.db, "update_image_keywords_for_image",
                        lambda image_id, csv, **kw: writes["sources"].append(kw["source_map"]))
    runner._process_bird_species_image_row(
        {"id": 3, "file_path": str(img)}, species_list=["Carolina Wren"], threshold=0.1, top_k=1,
        phase_code="bird_species", log=lambda *a, **kw: None)
    return runner.classifier.calls[0], writes


def test_region_mode_crops_region_writes_projection_and_marks_source(monkeypatch, tmp_path):
    projection = {"x1": 10, "y1": 20, "x2": 50, "y2": 60, "conf": 0.9, "img_w": 100, "img_h": 100}
    call, writes = _run_row(monkeypatch, tmp_path, use_regions=True,
                            choice={"mode": "region", "region": (0.1, 0.2, 0.5, 0.6)}, projection=projection)
    assert call == {"region": (0.1, 0.2, 0.5, 0.6), "use_detector": False}
    assert writes["bbox"] == [(3, projection)]
    assert writes["sources"] == [{"species:carolina wren": "bioclip_region"}]


def test_full_frame_mode_skips_detector(monkeypatch, tmp_path):
    call, writes = _run_row(monkeypatch, tmp_path, use_regions=True,
                            choice={"mode": "full_frame", "region": None}, projection={"detected": False})
    assert call == {"region": None, "use_detector": False}
    assert writes["bbox"] == [(3, {"detected": False})]
    assert writes["sources"] == [{"species:carolina wren": "bioclip"}]


def test_flag_off_is_the_legacy_path(monkeypatch, tmp_path):
    legacy = {"x1": 1, "y1": 2, "x2": 3, "y2": 4, "conf": 0.5, "img_w": 10, "img_h": 10}
    call, writes = _run_row(monkeypatch, tmp_path, use_regions=False,
                            choice={"mode": "region", "region": (0.1, 0.2, 0.5, 0.6)}, legacy_bbox=legacy)
    assert call == {"region": None, "use_detector": True}
    assert writes["bbox"] == [(3, legacy)]
    assert writes["sources"] == [{"species:carolina wren": "bioclip"}]
