"""Content-addressed crop cache (issue #375, AC-3 and AC-4).

No database, no GPU. Every test gets its own ``tmp_path`` cache directory.
"""

from __future__ import annotations

import os
import threading
import time

import pytest
from PIL import Image

from modules import crop_cache
from modules.crop_cache import crop_path, materialize_crop, prune_crop_cache
from modules.rendition import (
    CROP_POLICY_BIRD_V1,
    CROP_POLICY_TIGHT,
    CropPolicy,
    DecodeRoute,
    RenditionDescriptor,
    crop_cache_key,
)

REGION = (0.25, 0.25, 0.75, 0.75)


def _image(w=200, h=100):
    """A non-uniform image, so a crop in the wrong place would have different bytes."""
    img = Image.new("RGB", (w, h))
    for x in range(w):
        for y in range(h):
            img.putpixel((x, y), (x % 256, y % 256, (x * y) % 256))
    return img


def _descriptor(w=200, h=100, **over):
    base = dict(
        source_path="/photos/a.nef", source_hash="abc", source_hash_version="v1",
        decode_route=DecodeRoute.RAW_RAWPY, orientation=1,
        display_width=w, display_height=h,
    )
    base.update(over)
    return RenditionDescriptor(**base)


@pytest.fixture
def render_calls(monkeypatch):
    """Count how often pixels are actually produced (vs served from cache)."""
    calls = {"n": 0}
    real = crop_cache._render

    def _counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(crop_cache, "_render", _counting)
    return calls


# ---------------------------------------------------------------------------
# Hit / miss
# ---------------------------------------------------------------------------

def test_first_request_produces_the_crop(tmp_path, render_calls):
    path = materialize_crop(_image(), _descriptor(), REGION, CROP_POLICY_TIGHT, cache_dir=str(tmp_path))
    assert os.path.isfile(path)
    assert render_calls["n"] == 1
    assert Image.open(path).size == (100, 50)


def test_second_request_is_served_from_cache(tmp_path, render_calls):
    img, d = _image(), _descriptor()
    a = materialize_crop(img, d, REGION, CROP_POLICY_TIGHT, cache_dir=str(tmp_path))
    b = materialize_crop(img, d, REGION, CROP_POLICY_TIGHT, cache_dir=str(tmp_path))
    assert a == b
    assert render_calls["n"] == 1


def test_path_is_fanned_out_by_key_prefix(tmp_path):
    d = _descriptor()
    path = materialize_crop(_image(), d, REGION, CROP_POLICY_TIGHT, cache_dir=str(tmp_path))
    key = crop_cache_key(d, REGION, CROP_POLICY_TIGHT)
    assert path == os.path.join(str(tmp_path), key[:2], f"{key}.jpg")


def test_different_policy_is_a_different_artifact(tmp_path):
    img, d = _image(), _descriptor()
    a = materialize_crop(img, d, REGION, CROP_POLICY_TIGHT, cache_dir=str(tmp_path))
    b = materialize_crop(img, d, REGION, CROP_POLICY_BIRD_V1, cache_dir=str(tmp_path))
    assert a != b
    assert Image.open(b).size[0] > Image.open(a).size[0], "padding makes the crop wider"


def test_target_size_bounds_the_longest_edge(tmp_path):
    policy = CropPolicy(name="thumb", pad_frac=0.0, target_size=32)
    path = materialize_crop(_image(), _descriptor(), REGION, policy, cache_dir=str(tmp_path))
    assert max(Image.open(path).size) == 32


def test_png_policy_writes_a_png(tmp_path):
    policy = CropPolicy(name="lossless", image_format="PNG")
    path = materialize_crop(_image(), _descriptor(), REGION, policy, cache_dir=str(tmp_path))
    assert path.endswith(".png")
    assert Image.open(path).format == "PNG"


def test_refuses_an_image_that_is_not_the_described_rendition(tmp_path):
    """Caching a different rendition's pixels under this key would poison it."""
    with pytest.raises(ValueError, match="different rendition"):
        materialize_crop(_image(200, 100), _descriptor(100, 200), REGION, CROP_POLICY_TIGHT,
                         cache_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# AC-3 — eviction loses nothing
# ---------------------------------------------------------------------------

def test_evicted_crop_regenerates_byte_identically(tmp_path, render_calls):
    """The key is the durable identity; the file is disposable."""
    img, d = _image(), _descriptor()
    path = materialize_crop(img, d, REGION, CROP_POLICY_BIRD_V1, cache_dir=str(tmp_path))
    original = open(path, "rb").read()

    os.unlink(path)  # evict
    again = materialize_crop(img, d, REGION, CROP_POLICY_BIRD_V1, cache_dir=str(tmp_path))

    assert again == path
    assert open(again, "rb").read() == original
    assert render_calls["n"] == 2


def test_prune_removes_oldest_first_and_respects_the_budget(tmp_path):
    img, d = _image(), _descriptor()
    paths = []
    for i, region in enumerate([(0.0, 0.0, 0.5, 0.5), (0.5, 0.0, 1.0, 0.5), (0.0, 0.5, 0.5, 1.0)]):
        p = materialize_crop(img, d, region, CROP_POLICY_TIGHT, cache_dir=str(tmp_path))
        os.utime(p, (1_000_000 + i, 1_000_000 + i))  # deterministic ages, oldest first
        paths.append(p)

    sizes = [os.path.getsize(p) for p in paths]
    result = prune_crop_cache(sizes[1] + sizes[2], cache_dir=str(tmp_path))

    assert result["removed"] == 1
    assert not os.path.exists(paths[0]), "the oldest crop goes first"
    assert os.path.exists(paths[1]) and os.path.exists(paths[2])
    assert result["remaining_bytes"] <= sizes[1] + sizes[2]


def test_prune_to_zero_empties_the_cache(tmp_path):
    materialize_crop(_image(), _descriptor(), REGION, CROP_POLICY_TIGHT, cache_dir=str(tmp_path))
    assert prune_crop_cache(0, cache_dir=str(tmp_path))["remaining_bytes"] == 0


def test_prune_leaves_in_flight_temp_files_alone(tmp_path):
    """A .tmp file belongs to a writer mid-encode; deleting it would break that write."""
    tmp_file = tmp_path / "ab" / ".tmp-xyz.part"
    tmp_file.parent.mkdir()
    tmp_file.write_bytes(b"x" * 5000)
    prune_crop_cache(0, cache_dir=str(tmp_path))
    assert tmp_file.exists()


def test_a_stray_temp_file_is_never_served_as_a_hit(tmp_path, render_calls):
    """Only an os.replace()d file counts; an abandoned partial must not."""
    d = _descriptor()
    key = crop_cache_key(d, REGION, CROP_POLICY_TIGHT)
    stray = tmp_path / key[:2] / f".tmp-{key}.part"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"half a jpeg")

    path = materialize_crop(_image(), d, REGION, CROP_POLICY_TIGHT, cache_dir=str(tmp_path))
    assert render_calls["n"] == 1
    assert Image.open(path).size == (100, 50)


# ---------------------------------------------------------------------------
# AC-4 — concurrent requests coalesce
# ---------------------------------------------------------------------------

def test_concurrent_requests_for_one_key_produce_once(tmp_path, monkeypatch):
    """Sixteen threads, one key: the pixels are produced exactly once."""
    calls = {"n": 0}
    real = crop_cache._render
    barrier = threading.Barrier(16)

    def _slow_render(*a, **k):
        calls["n"] += 1
        time.sleep(0.05)  # widen the race window
        return real(*a, **k)

    monkeypatch.setattr(crop_cache, "_render", _slow_render)
    img, d = _image(), _descriptor()
    results, errors = [], []

    def _worker():
        try:
            barrier.wait()
            results.append(materialize_crop(img, d, REGION, CROP_POLICY_TIGHT, cache_dir=str(tmp_path)))
        except Exception as exc:  # pragma: no cover - surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert calls["n"] == 1
    assert len(set(results)) == 1
    assert Image.open(results[0]).size == (100, 50)


def test_different_keys_do_not_serialize_on_one_lock(tmp_path):
    """Per-key locks: unrelated crops must not queue behind each other."""
    a = crop_cache._key_lock("a" * 64)
    b = crop_cache._key_lock("b" * 64)
    assert a is not b
    assert crop_cache._key_lock("a" * 64) is a


def test_crop_path_uses_the_policy_extension(tmp_path):
    assert crop_path("ab" + "0" * 62, CROP_POLICY_TIGHT, str(tmp_path)).endswith(".jpg")


def test_uncoordinated_writers_never_error(tmp_path, monkeypatch):
    """Cross-process safety, simulated: with the in-process lock out of the picture every
    thread races to write the same key -- as separate processes would.

    Duplicate work is expected here; *errors* are not. On Windows the losing os.replace
    raises a sharing violation (PermissionError 13), which is how this was found: an
    earlier version claimed "the last rename wins", true only on POSIX.
    """
    monkeypatch.setattr(crop_cache, "_key_lock", lambda key: threading.Lock())
    real = crop_cache._render

    def _slow_render(*a, **k):
        time.sleep(0.02)
        return real(*a, **k)

    monkeypatch.setattr(crop_cache, "_render", _slow_render)
    img, d = _image(), _descriptor()
    barrier = threading.Barrier(16)
    results, errors = [], []

    def _worker():
        try:
            barrier.wait()
            results.append(materialize_crop(img, d, REGION, CROP_POLICY_TIGHT, cache_dir=str(tmp_path)))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"{len(errors)} writers failed: {errors[:2]!r}"
    assert len(set(results)) == 1
    assert Image.open(results[0]).size == (100, 50)
    leftovers = [n for _r, _d, fs in os.walk(tmp_path) for n in fs if n.startswith(".tmp-")]
    assert not leftovers, f"losing writers leaked temp files: {leftovers}"


def test_a_real_replace_failure_still_raises(tmp_path, monkeypatch):
    """The PermissionError is only swallowed when a winner's file is actually there."""
    def _refuse(src, dst):
        raise PermissionError(13, "denied")

    monkeypatch.setattr(crop_cache.os, "replace", _refuse)
    with pytest.raises(PermissionError):
        materialize_crop(_image(), _descriptor(), REGION, CROP_POLICY_TIGHT, cache_dir=str(tmp_path))
    leftovers = [n for _r, _d, fs in os.walk(tmp_path) for n in fs]
    assert not leftovers, "a failed write must not leave a temp file behind"
