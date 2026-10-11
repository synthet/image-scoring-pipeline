"""Stage 5 (#444, #592): bird_species consumes the active localization selection's region."""

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


def test_active_selection_selects_region(monkeypatch):
    conn = _Conn({"run_id": 7, "region_id": 9, "x1": 0.1, "y1": 0.2, "x2": 0.5, "y2": 0.6})
    _with_conn(monkeypatch, conn)
    choice = species_input_for_image(1)
    assert choice["mode"] == "region" and choice["region"] == (0.1, 0.2, 0.5, 0.6)
    assert (choice["run_id"], choice["region_id"]) == (7, 9)


def test_lookup_reads_active_selections_not_current_runs(monkeypatch):
    seen = []

    class _Spy(_Conn):
        def query_one(self, sql, params):
            seen.append(" ".join(sql.split()))
            return None

    _with_conn(monkeypatch, _Spy())
    species_input_for_image(1)
    assert "image_localization_selections" in seen[0] and "revoked_at IS NULL" in seen[0]
    assert "is_current" not in seen[0]


def test_no_selection_or_failed_lookup_falls_back_to_legacy(monkeypatch):
    for conn in (_Conn(None), _Conn({"run_id": 7, "region_id": None}), _Conn(exc=RuntimeError("db down"))):
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


def test_region_mode_crops_region_leaves_bbox_to_the_selection(monkeypatch, tmp_path):
    projection = {"x1": 10, "y1": 20, "x2": 50, "y2": 60, "conf": 0.9, "img_w": 100, "img_h": 100}
    call, writes = _run_row(monkeypatch, tmp_path, use_regions=True,
                            choice={"mode": "region", "region": (0.1, 0.2, 0.5, 0.6)}, projection=projection)
    assert call == {"region": (0.1, 0.2, 0.5, 0.6), "use_detector": False}
    # The selection is the only writer of bird_bbox for a selected image (#484).
    assert writes["bbox"] == []
    assert writes["sources"] == [{"species:carolina wren": "bioclip_region"}]


def test_flag_off_is_the_legacy_path(monkeypatch, tmp_path):
    legacy = {"x1": 1, "y1": 2, "x2": 3, "y2": 4, "conf": 0.5, "img_w": 10, "img_h": 10}
    call, writes = _run_row(monkeypatch, tmp_path, use_regions=False,
                            choice={"mode": "region", "region": (0.1, 0.2, 0.5, 0.6)}, legacy_bbox=legacy)
    assert call == {"region": None, "use_detector": True}
    assert writes["bbox"] == [(3, legacy)]
    assert writes["sources"] == [{"species:carolina wren": "bioclip"}]


def test_classify_abstains_at_exactly_the_threshold(monkeypatch):
    """#422: a probability equal to the floor abstains; only strictly above is kept."""
    import torch

    clf = bs.BioCLIPClassifier.__new__(bs.BioCLIPClassifier)
    clf.device = "cpu"
    clf.model = type("M", (), {"encode_image": lambda self, t: torch.tensor([[1.0, 0.0]])})()
    clf.preprocess = lambda img: torch.zeros(3, 2, 2)
    # Two identical text features -> softmax gives exactly 0.5 each.
    clf._get_text_features = lambda names: torch.tensor([[1.0, 0.0], [1.0, 0.0]])
    clf.load_model = lambda: None
    monkeypatch.setattr("modules.thumbnails.open_oriented_for_ml", lambda path: Image.new("RGB", (4, 4)))
    assert clf.classify("x.jpg", ["A", "B"], threshold=0.5, top_k=2, use_detector=False) == []
    assert len(clf.classify("x.jpg", ["A", "B"], threshold=0.49, top_k=2, use_detector=False)) == 2


def _abstain_row(monkeypatch, tmp_path, *, refresh, last_error):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    writes, exhausted = [], []
    runner = BirdSpeciesRunner()
    clf = _FakeClassifier()
    clf.classify = lambda *a, **kw: []
    clf.last_error = last_error
    runner.classifier = clf
    monkeypatch.setattr(bs, "use_regions_enabled", lambda: True)
    monkeypatch.setattr(bs, "species_input_for_image", lambda image_id: {"mode": "region", "region": (0, 0, 1, 1)})
    monkeypatch.setattr(runner, "_persist_bioclip_embedding", lambda image_id: None)
    monkeypatch.setattr(bs.db, "get_resolved_image_keywords",
                        lambda image_id, legacy_fallback=None, hide_internal=False: "birds,species:carolina wren,heron")
    monkeypatch.setattr("modules.bird_species_eligibility.build_bird_species_keyword_csv",
                        lambda image_id, legacy_csv, new_species: "birds,heron")
    monkeypatch.setattr(bs.db, "update_image_keywords_for_image", lambda image_id, csv, **kw: writes.append(csv))
    monkeypatch.setattr("modules.bird_species_eligibility.mark_species_exhausted",
                        lambda image_id: exhausted.append(image_id))
    runner._process_bird_species_image_row(
        {"id": 3, "file_path": str(img)}, species_list=["Carolina Wren"], threshold=0.5, top_k=1,
        phase_code="bird_species", log=lambda *a, **kw: None, refresh=refresh)
    return writes, exhausted


def test_refresh_abstention_clears_stale_species(monkeypatch, tmp_path):
    writes, exhausted = _abstain_row(monkeypatch, tmp_path, refresh=True, last_error=None)
    assert writes == ["birds,heron"] and exhausted == [3]


def test_refresh_keeps_species_when_classify_failed(monkeypatch, tmp_path):
    writes, exhausted = _abstain_row(monkeypatch, tmp_path, refresh=True, last_error="decode failed")
    assert writes == [] and exhausted == [3]


def test_abstention_without_refresh_preserves_species(monkeypatch, tmp_path):
    writes, _ = _abstain_row(monkeypatch, tmp_path, refresh=False, last_error=None)
    assert writes == []
