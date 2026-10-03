"""Tie-tolerant culling order (#508): rank gaps within culling.tie_tolerance are no evidence."""

from __future__ import annotations

import pytest

from modules.quality_ranking import parse_tie_tolerance, quality_tiebreak_sort_key_best_first
from modules.score_analytics.study import tie_tolerance_curve
from modules.selection import tie_tolerant_order
from modules.two_level_culling import TwoLevelConfig, process_stack_two_level


def _value(img):
    return float(img.get("score_general") or 0)


def _tiebreak(img):
    return (quality_tiebreak_sort_key_best_first(img), str(img.get("created_at") or ""), int(img["id"]))


def _sort_key(img):
    return (-_value(img), *_tiebreak(img))


def _img(i, score, iso=100, dto="2026:01:01 10:00:00"):
    return {"id": i, "score_general": score, "iso": iso, "exposure_time": "1/1000", "date_time_original": dto}


def test_zero_tolerance_matches_exact_ordering():
    group = [_img(1, 0.70), _img(2, 0.7001, iso=800), _img(3, 0.69), _img(4, 0.70, iso=50)]
    assert tie_tolerant_order(group, _value, _tiebreak, 0.0) == sorted(group, key=_sort_key)


def test_near_equal_scores_resolve_by_tiebreak_not_microscopic_gap():
    noisy = _img(1, 0.801, iso=800)
    clean = _img(2, 0.800, iso=100)
    assert [i["id"] for i in tie_tolerant_order([noisy, clean], _value, _tiebreak, 0.0)] == [1, 2]
    assert [i["id"] for i in tie_tolerant_order([noisy, clean], _value, _tiebreak, 0.005)] == [2, 1]


def test_equal_settings_tie_goes_to_earliest_capture_then_id():
    later = _img(1, 0.802, dto="2026:01:01 10:00:02")
    earlier = _img(2, 0.800, dto="2026:01:01 10:00:01")
    twin = _img(3, 0.800, dto="2026:01:01 10:00:01")
    ordered = tie_tolerant_order([later, earlier, twin], _value, _tiebreak, 0.005)
    assert [i["id"] for i in ordered] == [2, 3, 1]


def test_tiers_are_anchored_to_their_head_without_chaining():
    group = [_img(3, 0.80), _img(2, 0.795), _img(1, 0.79)]
    # 0.79 is within 0.006 of 0.795 but not of the tier head 0.80, so it stays below.
    assert [i["id"] for i in tie_tolerant_order(group, _value, _tiebreak, 0.006)] == [2, 3, 1]


@pytest.mark.parametrize("raw,expected", [(None, 0.0), ("abc", 0.0), (-0.01, 0.0), ({}, 0.0), ("0.01", 0.01)])
def test_parse_tie_tolerance_rejects_invalid_values(raw, expected):
    assert parse_tie_tolerance(raw) == expected


def test_two_level_uses_order_fn_when_given():
    images = [{"id": i, "score_general": i / 10, "file_path": ""} for i in range(1, 5)]
    cfg = TwoLevelConfig(picks_per_substack=1, diversity_enabled=False)
    _, default, _ = process_stack_two_level(1, images, {}, cfg, _sort_key)
    _, custom, _ = process_stack_two_level(
        1, images, {}, cfg, _sort_key, order_fn=lambda g: sorted(g, key=lambda im: im["id"])
    )
    assert [i for i, d, _ in default if d == "pick"] == [4]
    assert [i for i, d, _ in custom if d == "pick"] == [1]


def _groups(n, large_gap):
    """Grades [2, 1, 0]: frames 0/1 differ by 0.001 in alternating direction (chance
    ordering); frame 2 sits ``large_gap`` lower (always ordered correctly)."""
    out = []
    for k in range(n):
        sign = 1 if k % 2 else -1
        out.append({"id": f"g{k}", "grades": [2, 1, 0],
                    "scores": [0.5 + 0.0005 * sign, 0.5 - 0.0005 * sign, 0.5 - large_gap]})
    return out


def test_calibration_recommends_largest_chance_level_tolerance():
    # 300 near-tied pairs ordered at chance: CI upper bound ~0.56 <= 0.60 margin.
    result = tie_tolerance_curve(_groups(300, 0.0035), resamples=200)
    by_eps = {c["epsilon"]: c for c in result["curve"]}
    assert result["rule"] == "v2" and result["margin"] == 0.60
    assert by_eps[0.0025]["pairs"] == 300 and by_eps[0.0025]["qualifies"]
    assert by_eps[0.005]["pairs"] == 900 and by_eps[0.005]["eligible"] and not by_eps[0.005]["qualifies"]
    assert result["recommended_epsilon"] == 0.0025


def test_calibration_absence_of_evidence_does_not_qualify():
    # Run-1 shape: few chance-level pairs give a wide CI; v1 would have qualified it.
    result = tie_tolerance_curve(_groups(40, 0.0035), resamples=200)
    by_eps = {c["epsilon"]: c for c in result["curve"]}
    assert by_eps[0.0025]["eligible"] and by_eps[0.0025]["ci95"][1] > 0.60
    assert result["recommended_epsilon"] is None


def test_calibration_informative_score_does_not_qualify():
    groups = [{"id": f"g{k}", "grades": [2, 1], "scores": [0.501, 0.500]} for k in range(300)]
    result = tie_tolerance_curve(groups, resamples=200)
    assert result["recommended_epsilon"] is None
    assert all(not c["qualifies"] for c in result["curve"])


def test_calibration_smaller_failing_tolerance_blocks_larger_one():
    # Δ=0.001 pairs always agree (ε=0.0025 eligible, fails); adding the disagreeing
    # Δ≈0.004 pairs pulls cumulative agreement to 1/3, which alone would qualify.
    groups = [{"id": f"g{k}", "grades": [2, 1, 0], "scores": [0.5, 0.499, 0.5035]} for k in range(100)]
    result = tie_tolerance_curve(groups, resamples=200)
    by_eps = {c["epsilon"]: c for c in result["curve"]}
    assert by_eps[0.0025]["eligible"] and not by_eps[0.0025]["qualifies"]
    assert by_eps[0.005]["qualifies"]
    assert result["recommended_epsilon"] is None


def test_calibration_needs_enough_groups():
    result = tie_tolerance_curve(_groups(4, 0.0035), resamples=200)
    assert result["recommended_epsilon"] is None
    assert all(not c["eligible"] and not c["qualifies"] for c in result["curve"])


def test_calibration_reports_equal_grade_gaps():
    result = tie_tolerance_curve([{"id": "g", "grades": [2, 2, 0], "scores": [0.5, 0.49, 0.1]}], resamples=50)
    assert result["equal_grade_pairs"]["n"] == 1
    assert result["equal_grade_pairs"]["abs_delta_q25_50_75_90"][1] == pytest.approx(0.01)
