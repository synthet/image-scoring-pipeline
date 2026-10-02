"""Pure-logic guards for production localization selections (#484). No database."""

from modules.localization_selection import legacy_bbox_payload


def test_payload_matches_bird_detection_shape():
    p = legacy_bbox_payload({"x1": 0.25, "y1": 0.5, "x2": 0.5, "y2": 0.75, "confidence": 0.61234}, 6048, 4024)
    assert p == {"x1": 1512, "y1": 2012, "x2": 3024, "y2": 3018, "conf": 0.6123,
                 "img_w": 6048, "img_h": 4024, "area_frac": 0.0625}
    # The gallery and species code read exactly these keys; no provenance leaks into the JSON.
    assert set(p) == {"x1", "y1", "x2", "y2", "conf", "img_w", "img_h", "area_frac"}


def test_payload_without_confidence():
    p = legacy_bbox_payload({"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0, "confidence": None}, 100, 50)
    assert p["conf"] is None and p["area_frac"] == 1.0 and (p["x2"], p["y2"]) == (100, 50)


def test_promote_cli_clamps_float_overshoot_and_rejects_real_outliers():
    from scripts.maintenance.promote_localization_selections import clamp_region

    assert clamp_region([0.919192, 0.360949, 1.00004, 0.505676]) == (0.919192, 0.360949, 1.0, 0.505676)
    assert clamp_region([-0.0002, 0.1, 0.5, 0.6]) == (0.0, 0.1, 0.5, 0.6)
    assert clamp_region([0.2, 0.2, 1.05, 0.6]) is None          # genuinely outside: skipped, not written
    assert clamp_region([0.999, 0.1, 1.0004, 0.2]) == (0.999, 0.1, 1.0, 0.2)
    assert clamp_region([1.0, 0.1, 1.0004, 0.2]) is None         # degenerate after clamping
