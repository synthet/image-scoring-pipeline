"""Spec 03 (#408): RTMDet provider policy with a stub session (AC-2 to AC-5)."""

import hashlib
import json

import numpy as np
from PIL import Image

from modules.detectors import rtmdet


def _scores(n, entries):
    s = np.zeros((n, 80))
    for i, cls, v in entries:
        s[i, cls] = v
    return s


BOXES = np.array([[10, 10, 50, 50], [12, 12, 52, 52], [100, 100, 150, 140], [0, 0, 5, 5]], float)


def test_only_animal_classes_are_kept():
    s = _scores(4, [(0, 14, 0.9), (2, 0, 0.95), (3, 50, 0.9)])  # bird, person, broccoli
    assert [b["cls"] for b in rtmdet.select_animal_boxes(BOXES, s, 200, 200)] == ["bird"]


def test_per_class_nms_and_ranking():
    s = _scores(4, [(0, 14, 0.9), (1, 14, 0.8), (2, 21, 0.85)])  # two overlapping birds, one bear
    out = rtmdet.select_animal_boxes(BOXES, s, 200, 200)
    assert [(b["cls"], b["conf"]) for b in out] == [("bird", 0.9), ("bear", 0.85)]
    assert out[0]["region"] == (0.05, 0.05, 0.25, 0.25)
    assert out[0]["rank"] == 0


def test_retry_is_off_by_default():
    assert rtmdet.select_animal_boxes(BOXES, _scores(4, [(0, 14, 0.3)]), 200, 200) == []


def test_retry_threshold_only_when_nothing_reaches_the_main_one():
    def sel(s):
        return rtmdet.select_animal_boxes(BOXES, s, 200, 200, retry_threshold=0.25)

    assert [b["conf"] for b in sel(_scores(4, [(0, 14, 0.3)]))] == [0.3]
    assert [b["cls"] for b in sel(_scores(4, [(0, 14, 0.3), (2, 15, 0.5)]))] == ["cat"]
    assert sel(_scores(4, [(0, 14, 0.2)])) == []


def test_weights_mismatch_disables_provider(tmp_path):
    w = tmp_path / "m.onnx"
    w.write_bytes(b"onnx bytes")
    (tmp_path / "m.manifest.json").write_text(json.dumps({"onnx_sha256": "0" * 64}))
    p = rtmdet.load_rtmdet(str(w))
    assert not p.enabled
    assert p.error_code == rtmdet.ERROR_WEIGHTS_MISMATCH


def test_missing_manifest_is_unavailable(tmp_path):
    w = tmp_path / "m.onnx"
    w.write_bytes(b"onnx bytes")
    p = rtmdet.load_rtmdet(str(w))
    assert not p.enabled
    assert p.error_code == rtmdet.ERROR_UNAVAILABLE


def test_matching_hash_but_unloadable_model_does_not_raise(tmp_path):
    w = tmp_path / "m.onnx"
    w.write_bytes(b"onnx bytes")
    (tmp_path / "m.manifest.json").write_text(json.dumps({"onnx_sha256": hashlib.sha256(b"onnx bytes").hexdigest()}))
    p = rtmdet.load_rtmdet(str(w))
    assert not p.enabled
    assert p.error_code == rtmdet.ERROR_UNAVAILABLE


def test_detect_maps_letterbox_back_to_image_pixels():
    img = Image.new("RGB", (1280, 640))  # scale 0.5, pad_y 160

    class _Inp:
        name = "input"

    class _Session:
        def get_inputs(self):
            return [_Inp()]

        def run(self, _, feed):
            assert feed["input"].shape == (1, 3, 640, 640)
            assert feed["input"].dtype == np.float32
            boxes = np.array([[[100, 260, 200, 360]]], np.float32)  # letterbox pixels
            scores = np.zeros((1, 1, 80), np.float32)
            scores[0, 0, 14] = 0.9
            return [boxes, scores]

    p = rtmdet.RTMDetProvider(enabled=True, version="v", config_hash="h", session=_Session())
    assert p.detect(img)[0]["region"] == (200 / 1280, 200 / 640, 400 / 1280, 400 / 640)
