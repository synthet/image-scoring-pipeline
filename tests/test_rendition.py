"""Rendition descriptors, crop policy, cache keys and orientation (issue #375).

No database, no GPU, no model. The detector benchmark stage 3 also calls for is tracked
separately -- it needs `torch`/`ultralytics` and a GPU.

The orientation tests are the point of this module. EXIF orientations 5..8 transpose the
image, swapping width and height, so a region normalized against the *wrong* frame lands
somewhere plausible but wrong -- the failure mode is a crop that looks like a crop, just
not of the subject. Synthetic fixtures make that checkable without a photo library.
"""

from __future__ import annotations

import pytest

from modules.rendition import (
    COORD_SPACE_DISPLAY,
    CROP_POLICY_BIRD_V1,
    CROP_POLICY_TIGHT,
    SUSPICIOUS_AREA_FRAC,
    CropPolicy,
    RESIZING_ROUTES,
    DecodeRoute,
    RenditionDescriptor,
    area_frac,
    crop_cache_key,
    is_suspicious_geometry,
    normalize_pixel_box,
    padded_pixel_box,
    source_identity,
)

Image = pytest.importorskip("PIL.Image")
ImageOps = pytest.importorskip("PIL.ImageOps")


def _descriptor(**over):
    base = dict(
        source_path="/photos/a.nef",
        source_hash="abc123",
        source_hash_version="v1",
        decode_route=DecodeRoute.RAW_RAWPY,
        orientation=1,
        display_width=8256,
        display_height=5504,
    )
    base.update(over)
    return RenditionDescriptor(**base)


# ---------------------------------------------------------------------------
# RenditionDescriptor
# ---------------------------------------------------------------------------

def test_rendition_hash_ignores_the_path():
    """The same bytes decoded the same way are the same rendition after a move.

    Keying on path would invalidate every cached crop the first time a folder is
    reorganized, for pixels that did not change.
    """
    a = _descriptor(source_path="/photos/2024/a.nef")
    b = _descriptor(source_path="/archive/moved/b.nef")
    assert a.rendition_hash == b.rendition_hash


@pytest.mark.parametrize("field,value", [
    ("source_hash", "different"),
    ("source_hash_version", "v2"),
    ("decode_route", DecodeRoute.RAW_EMBEDDED_PREVIEW),
    ("orientation", 6),
    ("display_width", 4000),
    ("display_height", 3000),
    ("color_policy_version", "2"),
    ("descriptor_version", "2"),
])
def test_every_pixel_affecting_field_changes_the_hash(field, value):
    assert _descriptor().rendition_hash != _descriptor(**{field: value}).rendition_hash


def test_notes_are_informational_and_excluded():
    a = _descriptor()
    b = _descriptor(notes={"exiftool_tag": "JpgFromRaw"})
    assert a.rendition_hash == b.rendition_hash
    assert a == b, "notes must not affect equality either"


def test_descriptor_is_frozen():
    """A descriptor describes something that already happened."""
    d = _descriptor()
    with pytest.raises(Exception):
        d.orientation = 6  # type: ignore[misc]


@pytest.mark.parametrize("orientation", [0, 9, -1, 100])
def test_invalid_orientation_is_rejected(orientation):
    with pytest.raises(ValueError, match="orientation"):
        _descriptor(orientation=orientation)


@pytest.mark.parametrize("w,h", [(0, 100), (100, 0), (-1, 100)])
def test_non_positive_dimensions_are_rejected(w, h):
    with pytest.raises(ValueError, match="dimensions"):
        _descriptor(display_width=w, display_height=h)


def test_as_dict_states_the_coordinate_space():
    """Downstream must never have to guess which space a region lives in."""
    d = _descriptor().as_dict()
    assert d["coord_space"] == COORD_SPACE_DISPLAY
    assert d["rendition_hash"]
    assert d["decode_route"] == "raw_rawpy"


def test_source_identity_changes_with_content(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"a" * 1000)
    h1, v1 = source_identity(str(p))
    p.write_bytes(b"b" * 2000)
    h2, v2 = source_identity(str(p))
    assert h1 != h2
    assert v1 == v2, "the version tag moves only when the algorithm does"


# ---------------------------------------------------------------------------
# Orientation — EXIF 1..8 round trips (AC-1)
# ---------------------------------------------------------------------------

def _oriented_source(tmp_path, orientation: int, w=40, h=20):
    """A JPEG whose pixels are stored pre-transform, tagged with `orientation`.

    Built the way a camera writes one: take the upright image, apply the *inverse* of the
    display transform to get stored pixels, then tag it. `exif_transpose` on the result
    must reproduce the upright original.
    """
    upright = Image.new("RGB", (w, h), (10, 10, 10))
    # A marker in the upright top-left corner; where it lands proves the transform.
    for x in range(w // 4):
        for y in range(h // 4):
            upright.putpixel((x, y), (255, 0, 0))

    inverse = {
        1: None,
        2: Image.FLIP_LEFT_RIGHT,
        3: Image.ROTATE_180,
        4: Image.FLIP_TOP_BOTTOM,
        5: Image.TRANSPOSE,     # self-inverse
        6: Image.ROTATE_90,     # display applies ROTATE_270, so the inverse is ROTATE_90
        7: Image.TRANSVERSE,    # self-inverse
        8: Image.ROTATE_270,    # display applies ROTATE_90, so the inverse is ROTATE_270
    }[orientation]
    stored = upright if inverse is None else upright.transpose(inverse)

    path = tmp_path / f"o{orientation}.jpg"
    exif = Image.Exif()
    exif[0x0112] = orientation
    stored.save(path, "JPEG", exif=exif, quality=95)
    return path, upright


@pytest.mark.parametrize("orientation", [1, 2, 3, 4, 5, 6, 7, 8])
def test_orientation_round_trip_recovers_the_upright_frame(tmp_path, orientation):
    """Every EXIF orientation must transpose back to the same upright image.

    If this fails for 5..8, width and height are swapped and every normalized region
    computed against that rendition points at the wrong pixels.
    """
    path, upright = _oriented_source(tmp_path, orientation)
    displayed = ImageOps.exif_transpose(Image.open(path))

    assert displayed.size == upright.size, f"orientation {orientation} swapped dimensions"
    # The marker must be back in the top-left of the displayed frame.
    assert displayed.getpixel((2, 2))[0] > 200, f"orientation {orientation} misplaced the subject"
    assert displayed.getpixel((displayed.width - 3, displayed.height - 3))[0] < 100


@pytest.mark.parametrize("orientation", [5, 6, 7, 8])
def test_transposing_orientations_swap_stored_dimensions(tmp_path, orientation):
    """The reason display dimensions must be recorded, not inferred from the file."""
    path, upright = _oriented_source(tmp_path, orientation)
    stored = Image.open(path)
    assert stored.size == (upright.height, upright.width)
    assert ImageOps.exif_transpose(stored).size == upright.size


@pytest.mark.parametrize("orientation", [1, 2, 3, 4, 5, 6, 7, 8])
def test_same_region_crops_the_same_subject_across_orientations(tmp_path, orientation):
    """AC-1: one normalized region yields the same visual crop from any orientation.

    The region names the subject in *display* space. Whatever the file's stored
    orientation, cropping the display-oriented rendition must land on the marker.
    """
    path, upright = _oriented_source(tmp_path, orientation)
    displayed = ImageOps.exif_transpose(Image.open(path))

    region = (0.0, 0.0, 0.25, 0.25)  # the marker, in display space
    box = padded_pixel_box(region, displayed.width, displayed.height, CROP_POLICY_TIGHT)
    crop = displayed.crop(box)
    reference = upright.crop(
        padded_pixel_box(region, upright.width, upright.height, CROP_POLICY_TIGHT)
    )

    assert crop.size == reference.size
    assert crop.getpixel((1, 1))[0] > 200, f"orientation {orientation}: crop missed the subject"


# ---------------------------------------------------------------------------
# Crop policy and cache keys (AC-2)
# ---------------------------------------------------------------------------

def test_cache_key_is_stable_for_identical_inputs():
    d, r = _descriptor(), (0.1, 0.2, 0.6, 0.7)
    assert crop_cache_key(d, r, CROP_POLICY_BIRD_V1) == crop_cache_key(d, r, CROP_POLICY_BIRD_V1)


def test_cache_key_absorbs_sub_pixel_float_noise():
    """8256 * 1e-9 is far under one pixel; a miss there would be pure waste."""
    d = _descriptor()
    a = crop_cache_key(d, (0.1, 0.2, 0.6, 0.7), CROP_POLICY_BIRD_V1)
    b = crop_cache_key(d, (0.1 + 1e-9, 0.2, 0.6, 0.7), CROP_POLICY_BIRD_V1)
    assert a == b


def test_cache_key_changes_with_geometry_above_the_quantum():
    d = _descriptor()
    a = crop_cache_key(d, (0.1, 0.2, 0.6, 0.7), CROP_POLICY_BIRD_V1)
    b = crop_cache_key(d, (0.1001, 0.2, 0.6, 0.7), CROP_POLICY_BIRD_V1)
    assert a != b


@pytest.mark.parametrize("policy", [
    CropPolicy(name="bird_v1", pad_frac=0.20, version="1"),   # padding moved
    CropPolicy(name="bird_v1", pad_frac=0.10, version="2"),   # version bumped
    CropPolicy(name="other", pad_frac=0.10, version="1"),     # renamed
    CropPolicy(name="bird_v1", pad_frac=0.10, target_size=512, version="1"),
    CropPolicy(name="bird_v1", pad_frac=0.10, image_format="PNG", version="1"),
])
def test_every_policy_field_changes_the_cache_key(policy):
    """A config edit that changes crops must not reuse crops made under the old one."""
    d, r = _descriptor(), (0.1, 0.2, 0.6, 0.7)
    assert crop_cache_key(d, r, CROP_POLICY_BIRD_V1) != crop_cache_key(d, r, policy)


def test_cache_key_changes_with_the_rendition():
    d, r = _descriptor(), (0.1, 0.2, 0.6, 0.7)
    other = _descriptor(decode_route=DecodeRoute.RAW_EMBEDDED_PREVIEW)
    assert crop_cache_key(d, r, CROP_POLICY_BIRD_V1) != crop_cache_key(other, r, CROP_POLICY_BIRD_V1)


@pytest.mark.parametrize("region", [
    (0.5, 0.1, 0.2, 0.5),    # inverted x
    (0.1, 0.1, 0.1, 0.5),    # zero width
    (-0.1, 0.1, 0.5, 0.5),   # negative
    (0.1, 0.1, 1.5, 0.5),    # past the edge
])
def test_cache_key_rejects_unusable_geometry(region):
    with pytest.raises(ValueError):
        crop_cache_key(_descriptor(), region, CROP_POLICY_BIRD_V1)


def test_negative_padding_is_rejected():
    with pytest.raises(ValueError, match="pad_frac"):
        CropPolicy(name="x", pad_frac=-0.1)


# ---------------------------------------------------------------------------
# padded_pixel_box
# ---------------------------------------------------------------------------

def test_tight_policy_returns_the_box_itself():
    assert padded_pixel_box((0.25, 0.25, 0.75, 0.75), 100, 100, CROP_POLICY_TIGHT) == (25, 25, 75, 75)


def test_padding_scales_with_the_box_not_the_frame():
    """A distant bird gets a small margin, a close one a large margin."""
    small = padded_pixel_box((0.40, 0.40, 0.50, 0.50), 1000, 1000, CROP_POLICY_BIRD_V1)
    large = padded_pixel_box((0.10, 0.10, 0.90, 0.90), 1000, 1000, CROP_POLICY_BIRD_V1)
    assert (small[2] - small[0]) == pytest.approx(100 + 2 * 10, abs=2)
    assert (large[2] - large[0]) == pytest.approx(800 + 2 * 80, abs=2)


def test_padding_clamps_at_the_edge_without_shifting_the_subject():
    """Near an edge the crop grows less -- it is not slid inward.

    Shifting would move the subject off-centre and pull in context the detector never
    saw on that side.
    """
    box = padded_pixel_box((0.0, 0.0, 0.2, 0.2), 1000, 1000, CROP_POLICY_BIRD_V1)
    assert box[0] == 0 and box[1] == 0
    assert box[2] == pytest.approx(220, abs=2)


def test_sub_pixel_region_still_yields_at_least_one_pixel():
    """PIL raises on a zero-area crop, so rounding must not collapse the box."""
    box = padded_pixel_box((0.5, 0.5, 0.5001, 0.5001), 100, 100, CROP_POLICY_TIGHT)
    assert box[2] > box[0] and box[3] > box[1]


@pytest.mark.parametrize("region", [(0.5, 0.1, 0.2, 0.5), (0.1, 0.1, 1.2, 0.5)])
def test_padded_pixel_box_rejects_bad_geometry(region):
    with pytest.raises(ValueError):
        padded_pixel_box(region, 100, 100, CROP_POLICY_TIGHT)


# ---------------------------------------------------------------------------
# normalize_pixel_box and geometry metrics
# ---------------------------------------------------------------------------

def test_normalize_pixel_box_round_trips():
    assert normalize_pixel_box((100, 200, 600, 700), 1000, 1000) == pytest.approx(
        (0.1, 0.2, 0.6, 0.7)
    )


@pytest.mark.parametrize("box,w,h", [
    ((600, 200, 100, 700), 1000, 1000),   # inverted
    ((100, 200, 100, 700), 1000, 1000),   # zero width
    ((-10, 200, 600, 700), 1000, 1000),   # negative
    ((100, 200, 1600, 700), 1000, 1000),  # past the edge
    ((100, 200, 600, 700), 0, 1000),      # no frame
])
def test_normalize_pixel_box_rejects_rather_than_clamps(box, w, h):
    """Clamping would manufacture a plausible region nobody detected."""
    assert normalize_pixel_box(box, w, h) is None


def test_area_frac():
    assert area_frac((0.0, 0.0, 0.5, 0.5)) == pytest.approx(0.25)
    assert area_frac((0.0, 0.0, 1.0, 1.0)) == pytest.approx(1.0)


def test_suspicious_geometry_is_recorded_not_rejected():
    """The Sept 7 audit saw one accepted box at 93%. One outlier is not a threshold."""
    near_full = (0.0, 0.0, 0.97, 0.97)
    assert is_suspicious_geometry(near_full)
    # It must still produce a usable key and box -- flagged, not blocked.
    assert crop_cache_key(_descriptor(), near_full, CROP_POLICY_TIGHT)
    assert padded_pixel_box(near_full, 100, 100, CROP_POLICY_TIGHT)
    assert not is_suspicious_geometry((0.0, 0.0, 0.5, 0.5))
    assert SUSPICIOUS_AREA_FRAC < 1.0


# ---------------------------------------------------------------------------
# Decode route (AC-5) — open_rendition_for_ml reports which branch ran
# ---------------------------------------------------------------------------

def _raw_path(tmp_path):
    """A file with a RAW extension. Content is irrelevant: every decoder is stubbed."""
    p = tmp_path / "shot.nef"
    p.write_bytes(b"not really a nef")
    return str(p)


@pytest.fixture
def no_decoders(monkeypatch):
    """Every RAW route fails unless a test re-enables one."""
    from modules import thumbnails

    monkeypatch.setattr(thumbnails, "extract_embedded_jpeg", lambda *a, **k: None)
    monkeypatch.setattr(thumbnails.shutil, "which", lambda name: None)

    import rawpy
    def _fail(*a, **k):
        raise RuntimeError("rawpy disabled for this test")
    monkeypatch.setattr(rawpy, "imread", _fail)
    return thumbnails


def test_raster_file_reports_direct(tmp_path):
    from modules.thumbnails import open_rendition_for_ml

    p = tmp_path / "a.jpg"
    Image.new("RGB", (8, 4)).save(p)
    img, route = open_rendition_for_ml(str(p))
    assert route is DecodeRoute.DIRECT
    assert img.size == (8, 4)


def test_raw_embedded_preview_route(tmp_path, no_decoders, monkeypatch):
    preview = Image.new("RGB", (1200, 800))
    monkeypatch.setattr(no_decoders, "extract_embedded_jpeg", lambda *a, **k: preview)
    img, route = no_decoders.open_rendition_for_ml(_raw_path(tmp_path))
    assert route is DecodeRoute.RAW_EMBEDDED_PREVIEW
    assert img is preview


def test_raw_rawpy_route_when_no_preview(tmp_path, no_decoders, monkeypatch):
    import numpy as np
    import rawpy

    class _Raw:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def postprocess(self, **kw):
            return np.zeros((30, 40, 3), dtype=np.uint8)

    monkeypatch.setattr(rawpy, "imread", lambda p: _Raw())
    img, route = no_decoders.open_rendition_for_ml(_raw_path(tmp_path))
    assert route is DecodeRoute.RAW_RAWPY
    assert img.size == (40, 30)


def test_raw_imagemagick_route_as_last_resort(tmp_path, no_decoders, monkeypatch):
    import io
    import types

    buf = io.BytesIO()
    Image.new("RGB", (64, 48)).save(buf, "JPEG")
    monkeypatch.setattr(no_decoders.shutil, "which", lambda name: "/usr/bin/magick")
    monkeypatch.setattr(
        no_decoders.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stdout=buf.getvalue()),
    )
    img, route = no_decoders.open_rendition_for_ml(_raw_path(tmp_path))
    assert route is DecodeRoute.RAW_IMAGEMAGICK
    assert route in RESIZING_ROUTES, "the one route that resizes as a side effect"
    assert img.size == (64, 48)


def test_raw_with_every_route_failing_still_raises(tmp_path, no_decoders):
    from PIL import UnidentifiedImageError

    with pytest.raises(UnidentifiedImageError):
        no_decoders.open_rendition_for_ml(_raw_path(tmp_path))


def test_open_image_for_ml_is_unchanged_for_callers(tmp_path, no_decoders, monkeypatch):
    """Eleven callers across seven modules depend on the bare-Image return type."""
    preview = Image.new("RGB", (1200, 800))
    monkeypatch.setattr(no_decoders, "extract_embedded_jpeg", lambda *a, **k: preview)
    out = no_decoders.open_image_for_ml(_raw_path(tmp_path))
    assert out is preview
    assert not isinstance(out, tuple)


# ---------------------------------------------------------------------------
# build_rendition_descriptor
# ---------------------------------------------------------------------------

def test_build_descriptor_takes_dimensions_from_the_oriented_image(tmp_path):
    """For orientation 6 the display frame is the transpose of the stored one."""
    from modules.rendition import build_rendition_descriptor

    path, upright = _oriented_source(tmp_path, 6)
    displayed = ImageOps.exif_transpose(Image.open(path))
    d = build_rendition_descriptor(str(path), displayed, DecodeRoute.DIRECT, 6)
    assert (d.display_width, d.display_height) == upright.size
    assert d.orientation == 6
    assert d.source_hash


def test_build_descriptor_defaults_missing_orientation_to_1(tmp_path):
    from modules.rendition import build_rendition_descriptor

    p = tmp_path / "a.jpg"
    Image.new("RGB", (10, 5)).save(p)
    d = build_rendition_descriptor(str(p), Image.open(p), DecodeRoute.DIRECT, None)
    assert d.orientation == 1
