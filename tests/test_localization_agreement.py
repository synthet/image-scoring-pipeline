"""Spec 08 (#780): bird box agreement as pure functions (AC-4, AC-5)."""

import pytest

from modules.localization_agreement import (
    agreement_config_hash,
    agreement_score,
    padded_crop,
)

W, H = 1000, 500


def box(region, conf, cls="bird"):
    return {"region": region, "conf": conf, "cls": cls}


def test_padded_crop_pads_each_side_and_clamps_to_the_frame():
    # 200 x 100 px region at (100, 50), padded by 25% per side
    assert padded_crop((0.1, 0.1, 0.3, 0.3), W, H) == (50, 25, 350, 175)
    assert padded_crop((0.0, 0.0, 0.2, 0.2), W, H) == (0, 0, 250, 125)


def test_padded_crop_rejects_a_tiny_crop():
    assert padded_crop((0.5, 0.5, 0.501, 0.501), W, H) is None


def test_score_is_best_overlapping_bird():
    region = (0.1, 0.1, 0.3, 0.3)
    crop = (50, 25, 350, 175)
    # Crop-normalised boxes: the first matches the region exactly.
    exact = (50 / 300, 25 / 150, 250 / 300, 125 / 150)
    assert agreement_score(region, crop, [box(exact, 0.2), box(exact, 0.6)], W, H) == pytest.approx(0.6)


def test_score_ignores_other_classes_and_low_iou():
    region = (0.1, 0.1, 0.3, 0.3)
    crop = (50, 25, 350, 175)
    exact = (50 / 300, 25 / 150, 250 / 300, 125 / 150)
    corner = (0.0, 0.0, 0.1, 0.1)
    assert agreement_score(region, crop, [box(exact, 0.9, cls="cat"), box(corner, 0.9)], W, H) == 0.0


def test_score_is_zero_without_a_match():
    assert agreement_score((0.1, 0.1, 0.3, 0.3), (50, 25, 350, 175), [], W, H) == 0.0


def test_config_hash_covers_inputs():
    base = agreement_config_hash("rtmdet", "bird", 0.25, 0.3)
    assert base == agreement_config_hash("rtmdet", "bird", 0.25, 0.3)
    assert base != agreement_config_hash("other", "bird", 0.25, 0.3)
    assert base != agreement_config_hash("rtmdet", "other", 0.25, 0.3)
    assert base != agreement_config_hash("rtmdet", "bird", 0.5, 0.3)
    assert base != agreement_config_hash("rtmdet", "bird", 0.25, 0.5)
