"""Unit tests for autofocus metadata parsing and extraction."""

from __future__ import annotations
from pathlib import Path
import pytest

from modules.exif_extractor import (
    _parse_af_metadata,
    _parse_crop_area,
    extract_exif,
    _IMAGE_EXIF_UPSERT_KEYS,
)


def test_af_metadata_in_upsert_keys():
    assert "af_metadata" in _IMAGE_EXIF_UPSERT_KEYS


def test_parse_crop_area():
    assert _parse_crop_area("12 8 8256 5504") == [12, 8, 8256, 5504]
    assert _parse_crop_area("12, 8, 8256, 5504") == [12, 8, 8256, 5504]
    assert _parse_crop_area([12, 8, 8256, 5504]) == [12, 8, 8256, 5504]
    assert _parse_crop_area("") is None
    assert _parse_crop_area(None) is None
    assert _parse_crop_area("invalid") is None


def test_parse_af_metadata_mock():
    raw = {
        "AFInfo2Version": "0400",
        "AFAreaMode": 193,
        "AFAreaXPosition": 4128,
        "AFAreaYPosition": 2752,
        "AFAreaWidth": 291,
        "AFAreaHeight": 323,
        "AFImageWidth": 8256,
        "AFImageHeight": 5504,
        "CropArea": "12 8 8256 5504",
        "FocusResult": 1,
        "FocusDistance": 0.45,
    }
    af = _parse_af_metadata(raw)
    assert af is not None
    assert af["version"] == "0400"
    assert af["mode"] == "Single"
    assert af["in_focus"] is True
    assert af["area_x"] == 4128
    assert af["area_y"] == 2752
    assert af["af_image_w"] == 8256
    assert af["af_image_h"] == 5504
    assert af["crop_area"] == [12, 8, 8256, 5504]
    assert af["box"]["center_x"] == 0.5
    assert af["box"]["center_y"] == 0.5
    assert 0 < af["box"]["width"] < 1
    assert 0 < af["box"]["height"] < 1


def test_missing_focus_result_is_unknown_not_a_miss():
    """#672: Z6ii (AFInfo2 0301) writes no FocusResult; that is unknown, not ``in_focus=False``."""
    raw = {
        "AFInfo2Version": "0301",
        "AFAreaXPosition": 1404,
        "AFAreaYPosition": 1300,
        "AFAreaWidth": 285,
        "AFAreaHeight": 285,
        "AFImageWidth": 6048,
        "AFImageHeight": 4024,
    }
    assert _parse_af_metadata(raw)["in_focus"] is None
    assert _parse_af_metadata({**raw, "FocusResult": 0})["in_focus"] is False
    assert _parse_af_metadata({**raw, "ContrastDetectAFInFocus": "1"})["in_focus"] is True


def test_exiftool_version_is_cached(monkeypatch):
    from modules import exif_extractor

    calls = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        return type("R", (), {"stdout": "13.52\n"})()

    monkeypatch.setattr(exif_extractor, "_EXIFTOOL_VERSION", None)
    monkeypatch.setattr(exif_extractor, "_get_exiftool_path", lambda: "/usr/local/bin/exiftool")
    monkeypatch.setattr(exif_extractor.subprocess, "run", fake_run)
    assert exif_extractor.get_exiftool_version() == "13.52"
    assert exif_extractor.get_exiftool_version() == "13.52"
    assert calls == [["/usr/local/bin/exiftool", "-ver"]]


def test_parse_af_metadata_dx_crop():
    raw = {
        "AFInfo2Version": "0400",
        "AFAreaMode": 193,
        "AFAreaXPosition": 4128,
        "AFAreaYPosition": 2752,
        "AFAreaWidth": 300,
        "AFAreaHeight": 300,
        "AFImageWidth": 8256,
        "AFImageHeight": 5504,
        "CropArea": "1440 960 5376 3584",  # DX crop on FX sensor
        "FocusResult": "Focus",
    }
    af = _parse_af_metadata(raw)
    assert af is not None
    assert "crop_box" in af
    assert 0 < af["crop_box"]["width"] < 1
    assert 0 < af["crop_box"]["height"] < 1


def test_parse_af_metadata_missing():
    assert _parse_af_metadata({}) is None
    assert _parse_af_metadata({"AFAreaXPosition": 100}) is None


@pytest.mark.sample_data
def test_extract_exif_z8_af():
    fixture = Path("tests/fixtures/testing_samples/public/Z8/nikon_z8_01.nef")
    if not fixture.exists():
        pytest.skip("Z8 fixture not found")

    exif = extract_exif(str(fixture))
    assert exif is not None
    assert "af_metadata" in exif
    af = exif["af_metadata"]
    assert af["version"] == "0400"
    assert af["mode"] == "Single"
    assert af["in_focus"] is True
    assert af["box"]["center_x"] == 0.5
    assert af["box"]["center_y"] == 0.5


@pytest.mark.sample_data
def test_extract_exif_z6ii_af():
    fixture = Path("tests/fixtures/testing_samples/public/Z6II/nikon_z6_ii_01.nef")
    if not fixture.exists():
        pytest.skip("Z6II fixture not found")

    exif = extract_exif(str(fixture))
    assert exif is not None
    assert "af_metadata" in exif
    af = exif["af_metadata"]
    assert af["version"] == "0301"
    assert af["mode"] == "Wide (L)"
    assert af["in_focus"] is None  # the body writes no FocusResult (#672)
    assert af["box"]["width"] > 0
    assert af["box"]["height"] > 0
