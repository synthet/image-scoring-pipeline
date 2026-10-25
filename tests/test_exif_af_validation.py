"""AF evidence must not discard unrelated EXIF or serialize non-finite numbers."""

import json
from types import SimpleNamespace

import pytest

from modules import exif_extractor


@pytest.fixture
def af_record():
    return {
        "Model": "NIKON Z 8",
        "ISO": 12800,
        "DateTimeOriginal": "2026:10:17 14:26:03",
        "AFInfo2Version": "0400",
        "AFCoordinatesAvailable": 1,
        "AFImageWidth": 8256,
        "AFImageHeight": 5504,
        "AFAreaXPosition": 4303,
        "AFAreaYPosition": 1795,
        "AFAreaWidth": 304,
        "AFAreaHeight": 304,
        "FocusResult": 1,
    }


@pytest.mark.parametrize("field", [
    "AFImageWidth", "AFImageHeight", "AFAreaXPosition", "AFAreaYPosition",
    "AFAreaWidth", "AFAreaHeight",
])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True,
                                   "NaN", "Infinity", 10**400, []])
def test_invalid_af_geometry_is_unavailable(af_record, field, value):
    af_record[field] = value
    assert exif_extractor._parse_af_metadata(af_record) is None


@pytest.mark.parametrize("value", [0, "0", True, float("nan"), float("inf"), "unknown"])
def test_unavailable_or_invalid_coordinate_flag_blocks_geometry(af_record, value):
    af_record["AFCoordinatesAvailable"] = value
    assert exif_extractor._parse_af_metadata(af_record) is None


def test_absent_coordinate_flag_preserves_legacy_records(af_record):
    af_record.pop("AFCoordinatesAvailable")
    assert exif_extractor._parse_af_metadata(af_record) is not None


def test_overflowing_normalized_geometry_is_unavailable(af_record):
    af_record.update(AFAreaXPosition=-1.7e308, AFAreaWidth=1.7e308)
    assert exif_extractor._parse_af_metadata(af_record) is None


@pytest.mark.parametrize("field", ["AFImageWidth", "AFImageHeight", "AFAreaWidth", "AFAreaHeight"])
@pytest.mark.parametrize("value", [1e-300, 1.5])
def test_af_dimensions_are_positive_pixel_counts(af_record, field, value):
    af_record[field] = value
    assert exif_extractor._parse_af_metadata(af_record) is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), -1, True, 10**400])
def test_invalid_optional_distance_does_not_poison_af_evidence(af_record, value):
    af_record["FocusDistance"] = value
    evidence = exif_extractor._parse_af_metadata(af_record)
    assert evidence["focus_distance_m"] is None
    json.dumps(evidence, allow_nan=False)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, 10**400])
def test_invalid_numeric_mode_is_unknown(af_record, value):
    af_record["AFAreaMode"] = value
    evidence = exif_extractor._parse_af_metadata(af_record)
    assert evidence["mode"] == "Unknown"
    assert evidence["mode_code"] is None


@pytest.mark.parametrize("value", [[0, 0], [0, 0, 100, 100, 5],
                                  [0, 0, float("inf"), 100], [True, 0, 100, 100]])
def test_invalid_crop_area_is_unavailable(value):
    assert exif_extractor._parse_crop_area(value) is None


def test_observed_z8_geometry_stays_in_af_grid(af_record):
    af_record["CropArea"] = "12 8 8256 5504"
    evidence = exif_extractor._parse_af_metadata(af_record)
    assert evidence["box"]["left"] == pytest.approx((4303 - 152) / 8256, abs=1e-5)
    assert evidence["box"]["top"] == pytest.approx((1795 - 152) / 5504, abs=1e-5)
    assert evidence["crop_area"] == [12, 8, 8256, 5504]
    assert "crop_box" not in evidence


@pytest.mark.parametrize("af_updates", [{"AFAreaXPosition": "NaN"},
                                       {"AFCoordinatesAvailable": 0},
                                       {"CropArea": [0, 0, float("inf"), 100]}])
def test_extract_preserves_standard_exif_with_invalid_af(monkeypatch, tmp_path, af_record, af_updates):
    path = tmp_path / "source.NEF"
    path.write_bytes(b"metadata-only-test")
    af_record.update(af_updates)
    monkeypatch.setattr(exif_extractor, "_get_exiftool_path", lambda: "exiftool")
    monkeypatch.setattr(exif_extractor.utils, "resolve_file_path", lambda *args: str(path))
    monkeypatch.setattr(exif_extractor, "get_exiftool_timeout_seconds", lambda **kwargs: 30)
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps([af_record]), stderr="")

    monkeypatch.setattr(exif_extractor.subprocess, "run", run)
    result = exif_extractor.extract_exif(str(path))
    assert result is not None
    assert result["model"] == "NIKON Z 8"
    assert result["iso"] == 12800
    assert result["date_time_original"] == "2026:10:17 14:26:03"
    if "CropArea" in af_updates:
        assert result["af_metadata"]["crop_area"] is None
    else:
        assert result["af_metadata"] is None
        previous = {"af_metadata": {"box": {"left": 0.4}}, "f_number": 8}
        merged = exif_extractor._merge_exif_for_upsert(previous, result)
        assert merged["af_metadata"] is None
        assert merged["f_number"] == 8
    assert "-AFCoordinatesAvailable" in commands[0]


def test_unrelated_partial_extraction_preserves_cached_af():
    previous = {"af_metadata": {"box": {"left": 0.4}}, "f_number": 8}
    merged = exif_extractor._merge_exif_for_upsert(previous, {"iso": 400})
    assert merged["af_metadata"] == previous["af_metadata"]
    assert merged["f_number"] == 8
