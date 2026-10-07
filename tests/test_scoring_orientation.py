"""Orientation at the real quality-scoring preparation boundaries (no model load)."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

pytestmark = pytest.mark.ml  # Production module imports TensorFlow/rawpy.

# Expected corner order is independent of the production EXIF implementation.
CORNER_ORDERS = {
    1: (0, 1, 2, 3), 2: (1, 0, 3, 2), 3: (3, 2, 1, 0),
    4: (2, 3, 0, 1), 5: (0, 2, 1, 3), 6: (2, 0, 3, 1),
    7: (3, 1, 2, 0), 8: (1, 3, 0, 2),
}
COLORS = [(230, 30, 30), (30, 230, 30), (30, 30, 230), (230, 230, 30)]


def landmarks(size=(320, 160), orientation=None):
    image = Image.new("RGB", size)
    w, h = size
    for color, box in zip(COLORS, [(0, 0, w//2, h//2), (w//2, 0, w, h//2),
                                  (0, h//2, w//2, h), (w//2, h//2, w, h)]):
        image.paste(color, box)
    if orientation is not None:
        image.getexif()[274] = orientation
    return image


def jpeg_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=95, exif=image.getexif())
    return buffer.getvalue()


def assert_corners(path, orientation, *, padded=True, source_size=(320, 160)):
    with Image.open(path) as image:
        image.load()
        assert image.getexif().get(274, 1) == 1
        w, h = source_size
        if orientation >= 5:
            w, h = h, w
        if padded:
            assert image.size == (224, 224)
            factor = min(1, 224 / max(w, h))
            w, h = round(w * factor), round(h * factor)
            left, top = (224-w)//2, (224-h)//2
        else:
            assert image.size == (w, h)
            left, top = 0, 0
        pixels = [image.getpixel((left+x*w//4, top+y*h//4))
                  for x, y in [(1, 1), (3, 1), (1, 3), (3, 3)]]
        for actual, index in zip(pixels, CORNER_ORDERS[orientation]):
            assert max(abs(a-b) for a, b in zip(actual, COLORS[index])) < 12


@pytest.fixture
def converter(tmp_path, monkeypatch):
    import scripts.python.run_all_musiq_models as module

    instance = object.__new__(module.MultiModelMUSIQ)
    instance.project_root = str(tmp_path)
    instance.temp_dir = None
    instance.temp_files = []
    config = {"method": "exiftool_jpgfromraw", "max_resolution": 224,
              "jpeg_quality": 95, "exiftool_timeout_s": 1, "transient_retries": 0}
    monkeypatch.setattr(instance, "_get_raw_conversion_config", lambda: dict(config))
    monkeypatch.setattr(module, "_merged_app_config", lambda: {})
    return instance


@pytest.mark.parametrize("orientation", range(1, 9))
def test_scoring_applies_all_exif_transforms(converter, tmp_path, orientation):
    source = tmp_path / "input.png"
    landmarks(orientation=orientation).save(source, exif=landmarks(orientation=orientation).getexif())
    before = source.read_bytes()
    output = converter.preprocess_image(str(source), output_dir=str(tmp_path / "prepared"))
    assert output is not None
    assert_corners(output, orientation)
    assert source.read_bytes() == before


@pytest.mark.parametrize("orientation", range(1, 9))
def test_raw_preview_uses_source_orientation(converter, tmp_path, monkeypatch, orientation):
    from modules import thumbnails

    data = jpeg_bytes(landmarks())
    monkeypatch.setattr(converter, "_exiftool_extract_preview_bytes", lambda _: ("JpgFromRaw", data))
    monkeypatch.setattr(thumbnails, "read_orientation", lambda _: orientation)
    output = converter.preprocess_image(str(tmp_path / "source.NEF"), output_dir=str(tmp_path / "prepared"))
    assert_corners(output, orientation)


@pytest.mark.parametrize("embedded", [None, 1, 6])
def test_pipeline_raw_conversion_bakes_before_losing_source(converter, tmp_path, monkeypatch, embedded):
    from modules import thumbnails

    data = jpeg_bytes(landmarks(orientation=embedded))
    monkeypatch.setattr(converter, "_exiftool_extract_preview_bytes", lambda _: ("JpgFromRaw", data))
    monkeypatch.setattr(converter, "_is_safe_for_rawpy", lambda _: True)
    monkeypatch.setattr(thumbnails, "read_orientation", lambda _: 6)
    converted = converter.convert_raw_to_jpeg(str(tmp_path / "source.NEF"))
    assert converter.last_raw_conversion_route == "exiftool:JpgFromRaw"
    assert_corners(converted, 6, padded=False)
    prepared = converter.preprocess_image(converted, output_dir=str(tmp_path / "prepared"))
    assert_corners(prepared, 6)


def test_rawpy_output_is_not_rotated_twice(converter, tmp_path, monkeypatch):
    import scripts.python.run_all_musiq_models as module
    from modules import thumbnails

    upright = landmarks().transpose(Image.Transpose.ROTATE_270)
    raw = SimpleNamespace(postprocess=lambda **_: np.asarray(upright))
    class Context:
        def __enter__(self):
            return raw
        def __exit__(self, *_):
            pass
    monkeypatch.setattr(module.rawpy, "imread", lambda _: Context())
    monkeypatch.setattr(converter, "_is_safe_for_rawpy", lambda _: True)
    monkeypatch.setattr(converter, "_get_raw_conversion_config", lambda: {
        "method": "rawpy_half", "max_resolution": 224, "jpeg_quality": 95})
    monkeypatch.setattr(thumbnails, "read_orientation", lambda _: pytest.fail("rawpy pixels already oriented"))
    output = converter.preprocess_image(str(tmp_path / "source.NEF"), output_dir=str(tmp_path / "prepared"))
    assert_corners(output, 6)


@pytest.mark.parametrize("orientation", [None, 0, 9])
def test_missing_orientation_has_deterministic_fallback(converter, tmp_path, orientation):
    source = tmp_path / "input.png"
    image = landmarks(orientation=orientation)
    image.save(source, exif=image.getexif())
    output = converter.preprocess_image(str(source), output_dir=str(tmp_path / "prepared"))
    assert_corners(output, 1)


def test_square_tagged_input_is_not_mistaken_for_prepared_input(converter, tmp_path):
    source = tmp_path / "square.jpg"
    source.write_bytes(jpeg_bytes(landmarks((224, 224), orientation=6)))
    output = converter.preprocess_image(str(source))
    assert output != str(source)
    assert_corners(output, 6, source_size=(224, 224))


def test_prepared_input_is_upright_and_idempotent(converter, tmp_path):
    source = tmp_path / "input.jpg"
    source.write_bytes(jpeg_bytes(landmarks(orientation=6)))
    first = converter.preprocess_image(str(source))
    second = converter.preprocess_image(first)
    assert Path(second).read_bytes() == Path(first).read_bytes()
    assert_corners(second, 6)


def test_native_portrait_orientation_one_is_preserved(converter, tmp_path):
    source = tmp_path / "portrait.jpg"
    source.write_bytes(jpeg_bytes(landmarks((160, 320), orientation=1)))
    output = converter.preprocess_image(str(source), output_dir=str(tmp_path / "prepared"))
    assert_corners(output, 1, source_size=(160, 320))


def test_orientation_policy_invalidates_old_cache(converter, tmp_path, monkeypatch):
    import scripts.python.run_all_musiq_models as module

    source = tmp_path / "input.jpg"
    source.write_bytes(jpeg_bytes(landmarks(orientation=6)))
    config = {"preprocessing": {"cache_enabled": True},
              "raw_conversion": {"max_resolution": 224, "jpeg_quality": 95, "method": "rawpy_half"}}
    monkeypatch.setattr(module, "_merged_app_config", lambda: config)
    old_name = f'{hashlib.sha256(str(source).encode()).hexdigest()[:16]}_{int(source.stat().st_mtime)}.jpg'
    old = tmp_path / ".cache/preprocessed_224" / old_name
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old sideways cached input")
    new = converter._get_cache_path(str(source))
    assert new != str(old)
    output = converter.preprocess_image(str(source))
    assert_corners(output, 6)
    assert old.read_bytes() == b"old sideways cached input"
    config["raw_conversion"]["jpeg_quality"] = 85
    assert converter._get_cache_path(str(source)) != new


def test_scoring_executor_version_marks_orientation_policy():
    from modules.phases import SCORING_EXECUTOR_VERSION
    assert SCORING_EXECUTOR_VERSION != "5.0.0"


@pytest.mark.parametrize("orientation", range(1, 9))
def test_tiff_decoder_applies_orientation_once(converter, tmp_path, orientation):
    source = tmp_path / "input.tiff"
    image = landmarks(orientation=orientation)
    image.save(source, exif=image.getexif())
    output = converter.preprocess_image(str(source), output_dir=str(tmp_path / "prepared"))
    assert_corners(output, orientation)


@pytest.mark.parametrize("orientation", [None, 0, 9])
def test_invalid_preview_orientation_uses_source(converter, tmp_path, monkeypatch, orientation):
    from modules import thumbnails
    data = jpeg_bytes(landmarks(orientation=orientation))
    monkeypatch.setattr(converter, "_exiftool_extract_preview_bytes", lambda _: ("JpgFromRaw", data))
    monkeypatch.setattr(thumbnails, "read_orientation", lambda _: 8)
    output = converter.preprocess_image(str(tmp_path / "source.NEF"), output_dir=str(tmp_path / "prepared"))
    assert_corners(output, 8)


def test_valid_preview_tag_takes_precedence(converter, tmp_path, monkeypatch):
    from modules import thumbnails
    data = jpeg_bytes(landmarks(orientation=8))
    monkeypatch.setattr(converter, "_exiftool_extract_preview_bytes", lambda _: ("JpgFromRaw", data))
    monkeypatch.setattr(thumbnails, "read_orientation", lambda _: pytest.fail("usable preview tag exists"))
    output = converter.preprocess_image(str(tmp_path / "source.NEF"), output_dir=str(tmp_path / "prepared"))
    assert_corners(output, 8)


def test_direct_scoring_does_not_bypass_square_orientation(converter, tmp_path, monkeypatch):
    source = tmp_path / "square.jpg"
    source.write_bytes(jpeg_bytes(landmarks((224, 224), orientation=6)))
    converter.model_sources = {"spaq": "fake"}
    converter.models = {"spaq": object()}
    converter.model_ranges = {"spaq": (0, 100)}
    converter.gpu_available = False
    def predict(path, _name):
        assert_corners(path, 6, source_size=(224, 224))
        return 50
    monkeypatch.setattr(converter, "predict_quality", predict)
    result = converter.run_all_models(str(source), logger=lambda *_: None, write_metadata=False)
    assert result["models"]["spaq"]["status"] == "success"


def test_square_raw_input_returns_a_jpeg(converter, tmp_path, monkeypatch):
    from modules import thumbnails
    data = jpeg_bytes(landmarks((224, 224)))
    monkeypatch.setattr(converter, "_exiftool_extract_preview_bytes", lambda _: ("JpgFromRaw", data))
    monkeypatch.setattr(thumbnails, "read_orientation", lambda _: 1)
    output = converter.preprocess_image(str(tmp_path / "source.NEF"))
    assert_corners(output, 1, source_size=(224, 224))


def test_direct_scoring_rejects_failed_preparation(converter, tmp_path, monkeypatch):
    source = tmp_path / "input.jpg"
    source.write_bytes(jpeg_bytes(landmarks(orientation=6)))
    converter.model_sources = {"spaq": "fake"}
    converter.models = {"spaq": object()}
    converter.model_ranges = {"spaq": (0, 100)}
    converter.gpu_available = False
    calls = []
    monkeypatch.setattr(converter, "preprocess_image", lambda *_: None)
    monkeypatch.setattr(converter, "predict_quality", lambda *_: calls.append("inference") or 50)
    result = converter.run_all_models(str(source), logger=lambda *_: None, write_metadata=False)
    assert calls == []
    assert result["models"] == {}
    assert result["summary"]["error"] == "RAW/Image preprocessing failed"
