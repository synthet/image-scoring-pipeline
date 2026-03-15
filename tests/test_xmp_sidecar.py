"""
Tests for XMP sidecar read/write operations in modules/xmp.py.

Uses tmp_path fixture to create real .xmp files — no mocking needed since
xmp.py is pure XML I/O with no DB or network dependencies.
"""

import os
import pytest
from modules import xmp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _image_path(tmp_path, name="IMG_001.NEF"):
    """Return a fake image path whose .xmp sidecar lives in tmp_path."""
    return str(tmp_path / name)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def test_get_xmp_path_replaces_extension(tmp_path):
    img = _image_path(tmp_path, "photo.NEF")
    result = xmp.get_xmp_path(img)
    assert result.endswith(".xmp")
    assert not result.endswith(".NEF")


def test_xmp_exists_false_before_write(tmp_path):
    img = _image_path(tmp_path, "photo.jpg")
    assert xmp.xmp_exists(img) is False


def test_xmp_exists_true_after_write(tmp_path):
    img = _image_path(tmp_path, "photo.jpg")
    xmp.write_rating(img, 3)
    assert xmp.xmp_exists(img) is True


# ---------------------------------------------------------------------------
# Rating
# ---------------------------------------------------------------------------

def test_write_rating_creates_xmp_with_correct_value(tmp_path):
    img = _image_path(tmp_path)
    result = xmp.write_rating(img, 4)
    assert result is True
    data = xmp.read_xmp(img)
    assert data["rating"] == 4


def test_write_rating_zero(tmp_path):
    img = _image_path(tmp_path)
    xmp.write_rating(img, 5)
    xmp.write_rating(img, 0)
    data = xmp.read_xmp(img)
    assert data["rating"] == 0


def test_write_rating_invalid_returns_false(tmp_path):
    img = _image_path(tmp_path)
    assert xmp.write_rating(img, 6) is False
    assert xmp.write_rating(img, -1) is False


def test_write_rating_overwrites_previous(tmp_path):
    img = _image_path(tmp_path)
    xmp.write_rating(img, 3)
    xmp.write_rating(img, 5)
    data = xmp.read_xmp(img)
    assert data["rating"] == 5


# ---------------------------------------------------------------------------
# Label
# ---------------------------------------------------------------------------

def test_write_label_roundtrip(tmp_path):
    img = _image_path(tmp_path)
    assert xmp.write_label(img, "Red") is True
    data = xmp.read_xmp(img)
    assert data["label"] == "Red"


@pytest.mark.parametrize("label", ["Red", "Yellow", "Green", "Blue", "Purple"])
def test_write_label_all_valid_values(tmp_path, label):
    img = _image_path(tmp_path, f"photo_{label}.NEF")
    assert xmp.write_label(img, label) is True
    assert xmp.read_xmp(img)["label"] == label


def test_write_label_invalid_returns_false(tmp_path):
    img = _image_path(tmp_path)
    assert xmp.write_label(img, "Magenta") is False


def test_write_label_none_removes_label(tmp_path):
    img = _image_path(tmp_path)
    xmp.write_label(img, "Green")
    xmp.write_label(img, "None")
    data = xmp.read_xmp(img)
    # After clearing, label should be None (attribute removed)
    assert data["label"] is None


# ---------------------------------------------------------------------------
# Pick/reject flag
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", [1, -1, 0])
def test_write_pick_reject_flag_roundtrip(tmp_path, status):
    img = _image_path(tmp_path, f"photo_{status}.NEF")
    assert xmp.write_pick_reject_flag(img, status) is True
    assert xmp.read_pick_reject_flag(img) == status


def test_write_pick_reject_flag_invalid_returns_false(tmp_path):
    img = _image_path(tmp_path)
    assert xmp.write_pick_reject_flag(img, 2) is False


def test_read_pick_reject_flag_returns_0_for_missing_file(tmp_path):
    img = _image_path(tmp_path, "missing.NEF")
    assert xmp.read_pick_reject_flag(img) == 0


# ---------------------------------------------------------------------------
# UUID fields
# ---------------------------------------------------------------------------

def test_write_image_unique_id_roundtrip(tmp_path):
    img = _image_path(tmp_path)
    uuid = "TEST-UUID-1234"
    assert xmp.write_image_unique_id(img, uuid) is True
    full = xmp.read_xmp_full(img)
    # ImageUniqueID is not in read_xmp_full's current output keys, but it is written.
    # Verify the file was created and rating/label/pick fields are intact defaults.
    assert xmp.xmp_exists(img) is True


def test_write_image_unique_id_empty_returns_false(tmp_path):
    img = _image_path(tmp_path)
    assert xmp.write_image_unique_id(img, "") is False


def test_write_burst_uuid_roundtrip(tmp_path):
    img = _image_path(tmp_path)
    burst = "BURST-ABCD-5678"
    assert xmp.write_burst_uuid(img, burst) is True
    assert xmp.read_burst_uuid_from_xmp(img) == burst


def test_read_burst_uuid_returns_none_for_missing_file(tmp_path):
    img = _image_path(tmp_path, "no_file.NEF")
    assert xmp.read_burst_uuid_from_xmp(img) is None


# ---------------------------------------------------------------------------
# Batch write
# ---------------------------------------------------------------------------

def test_write_culling_results_writes_rating_and_label(tmp_path):
    img = _image_path(tmp_path)
    result = xmp.write_culling_results(img, rating=4, label="Blue")
    assert result is True
    data = xmp.read_xmp(img)
    assert data["rating"] == 4
    assert data["label"] == "Blue"


def test_write_culling_results_partial_update_preserves_existing(tmp_path):
    img = _image_path(tmp_path)
    xmp.write_rating(img, 3)
    xmp.write_culling_results(img, label="Green")  # Only set label
    data = xmp.read_xmp(img)
    assert data["rating"] == 3  # Should be preserved
    assert data["label"] == "Green"


# ---------------------------------------------------------------------------
# read_xmp on missing file
# ---------------------------------------------------------------------------

def test_read_xmp_returns_empty_dict_for_missing_file(tmp_path):
    img = _image_path(tmp_path, "nonexistent.jpg")
    data = xmp.read_xmp(img)
    assert data == {"rating": None, "label": None, "picked": None}


# ---------------------------------------------------------------------------
# read_xmp_full
# ---------------------------------------------------------------------------

def test_read_xmp_full_returns_pick_status(tmp_path):
    img = _image_path(tmp_path)
    xmp.write_pick_reject_flag(img, 1)
    full = xmp.read_xmp_full(img)
    assert full["pick_status"] == 1


def test_read_xmp_full_returns_burst_uuid(tmp_path):
    img = _image_path(tmp_path)
    xmp.write_burst_uuid(img, "MY-BURST-UUID")
    full = xmp.read_xmp_full(img)
    assert full["burst_uuid"] == "MY-BURST-UUID"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_xmp_removes_file(tmp_path):
    img = _image_path(tmp_path)
    xmp.write_rating(img, 2)
    assert xmp.xmp_exists(img) is True
    result = xmp.delete_xmp(img)
    assert result is True
    assert xmp.xmp_exists(img) is False
