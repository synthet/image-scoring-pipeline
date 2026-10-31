import numpy as np
from PIL import Image, ImageFilter

from modules.visual_evidence.compute import compute_maps, peaking_fields, measure_head


def scene():
    yy, xx = np.indices((256, 256))
    return ((np.sin(xx * .6) + np.sin(yy * .4)) * 45 + 128).clip(0, 255).astype(np.uint8)


def test_blur_reduces_noise_corrected_sharpness_and_peaking():
    sharp = scene()
    soft = np.asarray(Image.fromarray(sharp).filter(ImageFilter.GaussianBlur(3)))
    a, b = compute_maps(sharp), compute_maps(soft)
    assert np.mean(a["sharpness"]["values"]) > np.mean(b["sharpness"]["values"])
    first, second = peaking_fields(sharp), peaking_fields(soft)
    assert first["both"].sum() > second["both"].sum()


def test_noise_increases_estimate_but_flat_frames_do_not_peak():
    flat = np.full((256, 256), 128, np.uint8)
    noisy = np.clip(flat.astype(float) + np.random.default_rng(42).normal(0, 8, flat.shape), 0, 255).astype(np.uint8)
    a, b = compute_maps(flat), compute_maps(noisy)
    assert np.mean(b["noise"]["values"]) > np.mean(a["noise"]["values"])
    assert not peaking_fields(flat)["both"].any()
    assert np.count_nonzero(peaking_fields(noisy)["both"]) / flat.size < .01


def test_clean_edges_are_not_reported_as_noise_and_grid_covers_remainders():
    edge = np.zeros((137, 149), np.uint8)
    edge[:, 70:] = 255
    result = compute_maps(edge)
    noise = [value for value in result["noise"]["values"] if value is not None]
    assert noise and max(noise) < .01
    for grid in result.values():
        assert len(grid["values"]) == grid["cells_x"] * grid["cells_y"]
        assert all(value is None or 0 <= value <= 1 for value in grid["values_normalized"])
        assert grid["x_edges"][-1] == 149 and grid["y_edges"][-1] == 137


def test_head_measurement_separates_reliability_from_quality():
    points = [{"name": "left_eye", "x": .4, "y": .4, "confidence": .95},
              {"name": "head_top", "x": .4, "y": .3, "confidence": .95},
              {"name": "beak", "x": .6, "y": .45, "confidence": .95}]
    result = measure_head(scene(), points, (.2, .2, .8, .8))
    assert result["head_bbox"]
    assert result["facing_vector"]
    assert result["eyes"][0]["evidence_confidence"] == .95
    assert "sharpness_ratio" in result["eyes"][0]
    assert "band" not in result["eyes"][0]
