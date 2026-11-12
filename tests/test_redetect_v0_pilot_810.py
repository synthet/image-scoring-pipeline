"""Unit tests for the #810 pilot re-detection script's pure helpers (no DB, no GPU)."""
import pytest

from scripts.maintenance import redetect_v0_pilot_810 as p


def _row(**kw):
    base = {"detector_version": p.V0_VERSION, "status": "detected", "region_id": 5,
            "has_legacy_payload": False}
    base.update(kw)
    return base


@pytest.mark.parametrize("row,expected", [
    (None, "no_current_bird_run"),
    (_row(detector_version=p.V1_VERSION), "current_run_not_v0"),
    (_row(status="no_detection"), "v0_not_detected"),
    (_row(region_id=None), "v0_not_detected"),
    (_row(has_legacy_payload=True), "has_legacy_payload"),
    (_row(), "eligible"),
])
def test_eligibility(row, expected):
    assert p.eligibility(row) == expected


def test_terciles_split_pool_evenly():
    areas = [i / 30 for i in range(30)]
    cuts = p.tercile_cuts(areas)
    strata = [p.stratum_for(a, cuts) for a in areas]
    assert strata.count("small") == strata.count("medium") == strata.count("large") == 10


def _pool(n=90):
    cuts = (0.1, 0.2)
    pool = []
    for i in range(n):
        area = (i % 3) * 0.1 + 0.05
        pool.append({"image_id": i, "stratum": p.stratum_for(area, cuts)})
    return pool


def test_draw_is_seeded_stratified_and_sized():
    a = p.draw_stratified(_pool(), seed=810, size=20)
    b = p.draw_stratified(_pool(), seed=810, size=20)
    assert a == b and len(a) == 20
    counts = {s: sum(f["stratum"] == s for f in a) for s in p.STRATA}
    assert counts == {"small": 7, "medium": 7, "large": 6}
    assert p.draw_stratified(_pool(), seed=811, size=20) != a


def test_draw_refuses_short_stratum():
    with pytest.raises(ValueError):
        p.draw_stratified(_pool(6), seed=1, size=9)


def test_result_record_detected_and_skipped():
    det = p.result_record(1, {"run_id": 9, "status": "detected", "detector_version": p.V1_VERSION,
                              "region_id": 3, "x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4,
                              "confidence": 0.9, "display_width": 10, "display_height": 8}, 1.23456)
    assert det["v1"]["box"] == [0.1, 0.2, 0.3, 0.4] and det["v1"]["skip_reason"] is None
    assert det["seconds"] == 1.235
    skip = p.result_record(2, {"run_id": 10, "status": "disabled", "error_code": "scene_route",
                               "region_id": None}, 0.5)
    assert skip["v1"]["status"] == "disabled" and skip["v1"]["box"] is None
    assert skip["v1"]["skip_reason"] == "scene_route"
    assert p.result_record(3, None, 0.0)["v1"]["status"] == "missing"


def test_rollback_restores_v0_and_demotes_new_run():
    manifest = {"frames": [{"image_id": 1, "v0": {"run_id": 100}}, {"image_id": 2, "v0": {"run_id": 200}}]}
    results = [{"image_id": 1, "v1": {"run_id": 101}}, {"image_id": 2, "v1": {"run_id": 200}},
               {"image_id": 3, "v1": {"run_id": 301}}]
    sql = p.rollback_statements(manifest, results)
    assert sql == [
        "UPDATE image_localization_runs SET is_current = FALSE WHERE id = 101 AND image_id = 1;",
        "UPDATE image_localization_runs SET is_current = TRUE WHERE id = 100 AND image_id = 1;",
    ]
