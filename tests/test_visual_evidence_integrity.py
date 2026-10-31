"""Runtime evidence must describe real pixels; RLE has a background-first contract."""
from types import SimpleNamespace

import numpy as np
import pytest

from modules.visual_evidence import rle, service


@pytest.mark.parametrize("mask", [np.zeros((3, 4), bool), np.ones((3, 4), bool), np.eye(4, dtype=bool), np.array([[True, False], [False, True]])])
def test_rle_background_first_roundtrip(mask):
    width, height, counts = rle.encode_mask_rle(mask)
    if mask[0, 0]:
        assert counts[0] == 0
    assert sum(counts) == width * height
    assert np.array_equal(rle.decode_mask_rle(width, height, counts), mask)


@pytest.mark.parametrize("counts", [[1], [-1, 5], [2, 3], [1.5, 2.5]])
def test_rle_rejects_corrupt_counts(counts):
    with pytest.raises(ValueError):
        rle.decode_mask_rle(2, 2, counts)


def _row(monkeypatch, payload):
    cursor = SimpleNamespace(execute=lambda *args: None, fetchone=lambda: payload)
    connection = SimpleNamespace(cursor=lambda: cursor, close=lambda: None)
    monkeypatch.setattr(service.db, "get_db", lambda: connection)
    monkeypatch.setattr(service, "overlay_bird_bboxes", lambda rows: None)
    monkeypatch.setattr(service, "_rendition_hash", lambda *args: "test-rendition")


def test_missing_source_never_returns_demonstration_evidence(monkeypatch):
    _row(monkeypatch, ("missing.jpg", None))
    monkeypatch.setattr(service, "_load_grey_from_thumbnail", lambda _: None)
    result = service.build_evidence_for_image(42)
    assert result.image_id == 42
    assert not any(result.gates.model_dump().values())
    assert result.focus_grid is None and result.mask_rle is None
    assert result.criteria == []
    assert "source_unavailable" in result.limitations


def test_box_is_not_exposed_as_segmentation(monkeypatch):
    _row(monkeypatch, ("preview.jpg", {"x1": 8, "y1": 8, "x2": 32, "y2": 32, "img_w": 64, "img_h": 64, "conf": .99}))
    monkeypatch.setattr(service, "_load_grey_from_thumbnail", lambda _: np.arange(4096, dtype=np.uint8).reshape(64, 64))
    result = service.build_evidence_for_image(42)
    assert result.gates.region
    assert not result.gates.mask
    assert result.mask_rle is None
    assert result.criteria == []


def test_legacy_preview_uses_existing_platform_path_resolver(monkeypatch, tmp_path):
    from PIL import Image
    source = tmp_path / "preview.png"
    Image.new("RGB", (40, 24), (80, 80, 80)).save(source)
    monkeypatch.setattr(service, "resolve_to_existing", lambda path: str(source))
    raster = service._load_grey_from_thumbnail("Z:\\unavailable\\preview.png")
    assert raster.shape == (24, 40)
    assert int(raster.mean()) == 80
