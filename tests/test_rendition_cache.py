"""Spec 01 (#406) slice 1: decode-once rendition cache (AC-1, AC-4, AC-5, AC-6)."""

import os

import pytest
from PIL import Image

import modules.rendition_cache as rc
from modules.localization import Decoded
from modules.rendition import DecodeRoute, build_rendition_descriptor


@pytest.fixture
def raw_file(tmp_path):
    p = tmp_path / "DSC_0001.NEF"
    p.write_bytes(b"not really a raw" * 100)
    return p


@pytest.fixture
def fake_decoder(monkeypatch):
    calls = []

    def decode(path):
        calls.append(path)
        img = Image.new("RGB", (6000, 4000), (40, 120, 200))
        img.putpixel((10, 10), (255, 0, 0))
        return Decoded(image=img, descriptor=build_rendition_descriptor(
            path, img, DecodeRoute.RAW_JPG_FROM_RAW, 6))

    monkeypatch.setattr("modules.localization.decode_for_localization", decode)
    return calls


def test_miss_writes_jpeg_and_descriptor_at_2048(raw_file, tmp_path, fake_decoder):
    img, desc, info = rc.get_inference_rendition(str(raw_file), cache_dir=str(tmp_path / "c"))
    assert info["cache"] == "miss" and len(fake_decoder) == 1
    assert img.size == (2048, 1365) and (desc.display_width, desc.display_height) == img.size
    assert desc.decode_route is DecodeRoute.RAW_JPG_FROM_RAW and desc.orientation == 6
    assert desc.notes["full_width"] == 6000
    jpg, meta = rc.rendition_paths(rc.rendition_key(desc.source_hash, desc.source_hash_version),
                                   str(tmp_path / "c"))
    assert os.path.isfile(jpg) and os.path.isfile(meta)
    # AC-4 layout: <cache>/<key[:2]>/<key>.jpg
    assert os.path.basename(os.path.dirname(jpg)) == os.path.basename(jpg)[:2]


def test_hit_does_not_decode_and_returns_same_pixels(raw_file, tmp_path, fake_decoder):
    a, da, _ = rc.get_inference_rendition(str(raw_file), cache_dir=str(tmp_path / "c"))
    b, db_, info = rc.get_inference_rendition(str(raw_file), cache_dir=str(tmp_path / "c"))
    assert info["cache"] == "hit" and len(fake_decoder) == 1
    assert a.tobytes() == b.tobytes() and da.rendition_hash == db_.rendition_hash


def test_evicted_rendition_regenerates_byte_identically(raw_file, tmp_path, fake_decoder):
    cache = str(tmp_path / "c")
    _, desc, _ = rc.get_inference_rendition(str(raw_file), cache_dir=cache)
    jpg, meta = rc.rendition_paths(rc.rendition_key(desc.source_hash, desc.source_hash_version), cache)
    first = open(jpg, "rb").read()
    os.unlink(jpg)
    os.unlink(meta)
    rc.get_inference_rendition(str(raw_file), cache_dir=cache)
    assert open(jpg, "rb").read() == first  # AC-5


def test_changed_source_gets_a_new_key(raw_file, tmp_path, fake_decoder):
    cache = str(tmp_path / "c")
    _, d1, _ = rc.get_inference_rendition(str(raw_file), cache_dir=cache)
    raw_file.write_bytes(b"edited raw bytes" * 200)
    _, d2, info = rc.get_inference_rendition(str(raw_file), cache_dir=cache)
    assert info["cache"] == "miss" and d1.source_hash != d2.source_hash


def test_non_raw_sources_are_not_cached(tmp_path, fake_decoder):
    jpg = tmp_path / "a.jpg"
    Image.new("RGB", (100, 50)).save(jpg)
    img, _, info = rc.get_inference_rendition(str(jpg), cache_dir=str(tmp_path / "c"))
    assert info["cache"] == "direct" and not (tmp_path / "c").exists()


def test_prune_removes_least_recently_used_pairs(tmp_path, fake_decoder):
    cache = str(tmp_path / "c")
    for n in range(3):
        f = tmp_path / f"DSC_{n}.NEF"
        f.write_bytes(bytes([n]) * 5000)
        rc.get_inference_rendition(str(f), cache_dir=cache)
    jpgs = sorted((tmp_path / "c").glob("*/*.jpg"))
    for age, j in enumerate(jpgs):  # jpgs[-1] is the most recently used
        for f in (j, j.with_suffix(".json")):
            os.utime(f, (1000 + age, 1000 + age))
    one = jpgs[-1].stat().st_size + jpgs[-1].with_suffix(".json").stat().st_size
    res = rc.prune_rendition_cache(one + 10, cache_dir=cache)
    assert res["removed"] == 2
    assert list((tmp_path / "c").glob("*/*.jpg")) == [jpgs[-1]]
    assert jpgs[-1].with_suffix(".json").exists()
