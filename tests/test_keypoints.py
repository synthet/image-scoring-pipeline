"""Pure helpers of the shadow keypoint provider (#426); no model, no database."""

import pytest

from modules.keypoints import (
    KEYPOINT_NAMES,
    STATUS_DETECTED,
    STATUS_NO_KEYPOINTS,
    is_unchanged,
    keypoints_config,
    padded_crop_box,
    select_detection,
    to_display_normalized,
)


def test_padded_crop_box_pads_and_clamps():
    # 0.1 .. 0.3 of a 1000x500 frame: 200x100 px box, 25% pad -> 50 px / 25 px.
    assert padded_crop_box((0.1, 0.2, 0.3, 0.4), 1000, 500, 0.25) == (50, 75, 350, 225)
    # Touching the frame edge clamps instead of going negative.
    assert padded_crop_box((0.0, 0.0, 0.5, 0.5), 100, 100, 0.25) == (0, 0, 62, 62)


def test_padded_crop_box_rejects_degenerate():
    assert padded_crop_box((0.5, 0.5, 0.5001, 0.5001), 100, 100, 0.0) is None


def test_select_detection_prefers_region_overlap_over_confidence():
    target = (100, 100, 200, 200)
    neighbour = {"xyxy": (0, 0, 60, 60), "conf": 0.99, "kpts": []}  # brought in by padding
    ours = {"xyxy": (105, 95, 205, 210), "conf": 0.40, "kpts": []}
    assert select_detection([neighbour, ours], target) is ours
    assert select_detection([neighbour], target) is None


def test_to_display_normalized_maps_crop_to_frame_and_gates_visibility():
    kpts = [(10, 20, 0.9), (50, 50, 0.1)] + [(0, 0, 0.0)] * 4
    rows = to_display_normalized(kpts, (100, 200, 300, 400), 1000, 800, 0.25)
    assert [r["name"] for r in rows] == list(KEYPOINT_NAMES)
    assert rows[0]["x"] == pytest.approx(0.11) and rows[0]["y"] == pytest.approx(0.275)
    assert rows[0]["visible"] is True and rows[1]["visible"] is False


def test_is_unchanged_only_for_final_answers_from_same_config():
    assert is_unchanged({"status": STATUS_DETECTED, "provider_config_hash": "h"}, "h")
    assert is_unchanged({"status": STATUS_NO_KEYPOINTS, "provider_config_hash": "h"}, "h")
    assert not is_unchanged({"status": "retryable_error", "provider_config_hash": "h"}, "h")
    assert not is_unchanged({"status": STATUS_DETECTED, "provider_config_hash": "old"}, "h")
    assert not is_unchanged(None, "h")


def test_keypoints_config_defaults_off():
    cfg = keypoints_config({})
    assert cfg["enabled"] is False and cfg["model_repo"] == "synthet/eye-pose-v0"
    assert keypoints_config({"keypoints": {"bird_head": {"crop_pad": 0.5}}})["crop_pad"] == 0.5
