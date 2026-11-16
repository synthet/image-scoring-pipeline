"""Pure logic of the #879 v0/v1 detector comparison (no model, no DB)."""
import json

import pytest

from scripts.research import detector_compare_879 as DC

BOX = [0.1, 0.1, 0.5, 0.5]


def _row(i, s, v0=BOX, v1=BOX):
    return {"image_id": i, "stratum": s, "v0": {"box": v0}, "v1": {"box": v1}}


@pytest.mark.parametrize("v0,v1,expected", [
    (None, None, "N"),
    (BOX, None, "O0"),
    (None, BOX, "O1"),
    (BOX, BOX, "A"),
    (BOX, [0.3, 0.1, 0.7, 0.5], "P"),          # IoU 1/3
    (BOX, [0.6, 0.6, 0.9, 0.9], "D"),          # disjoint
])
def test_stratum(v0, v1, expected):
    assert DC.stratum(v0, v1) == expected


def test_draw_capped_is_seeded_capped_and_sorted():
    pool = [{"image_id": i, "shoot": f"s{i % 4}"} for i in range(40, 0, -1)]
    a = DC.draw_capped(pool, seed=879, size=12, cap=3)
    assert a == DC.draw_capped(list(reversed(pool)), seed=879, size=12, cap=3)
    assert max(sum(f["shoot"] == s for f in a) for s in {f["shoot"] for f in a}) <= 3
    assert [f["image_id"] for f in a] == sorted(f["image_id"] for f in a)
    with pytest.raises(ValueError):
        DC.draw_capped(pool, seed=1, size=13, cap=3)


def test_select_for_review_takes_all_disagreements_and_a_spot_check():
    rows = [_row(i, "A") for i in range(50)] + [_row(100 + i, "N", None, None) for i in range(5)] + \
           [_row(200, "O0", BOX, None), _row(201, "O1", None, BOX), _row(202, "D", BOX, [0.6, 0.6, 0.9, 0.9])]
    rev = DC.select_for_review(rows, spot=10, seed=879)
    assert rev["counts"]["A"] == 50 and len(rev["review"]["A"]) == 10
    assert len(rev["review"]["N"]) == 5                       # fewer than the spot size: take all
    assert rev["review"]["O0"] == [200] and rev["review"]["O1"] == [201] and rev["review"]["D"] == [202]
    assert rev == DC.select_for_review(list(reversed(rows)), spot=10, seed=879)


def test_frame_outcome():
    o = DC.frame_outcome(_row(1, "O0", BOX, None), {"bird": "yes", "v0": "bird", "v1": None})
    assert o["v0"] == {"box": True, "fp": False, "hit": True, "miss": False}
    assert o["v1"] == {"box": False, "fp": False, "hit": False, "miss": True}
    o = DC.frame_outcome(_row(2, "O0", BOX, None), {"bird": "no", "v0": "not", "v1": None})
    assert o["v0"]["fp"] and not o["v0"]["miss"] and not o["v1"]["miss"]
    assert DC.frame_outcome(_row(3, "A"), {"bird": "unsure"}) is None


def test_estimate_weights_spot_checked_strata_back_to_the_sample():
    rows = [_row(i, "A") for i in range(40)] + [_row(100, "O0", BOX, None), _row(101, "O1", None, BOX)]
    review = {"counts": {"N": 0, "A": 40, "P": 0, "D": 0, "O0": 1, "O1": 1},
              "review": {"N": [], "A": [0, 1, 2, 3], "P": [], "D": [], "O0": [100], "O1": [101]}}
    labels = {"0": {"bird": "yes", "v0": "bird", "v1": "bird"}, "1": {"bird": "yes", "v0": "bird", "v1": "bird"},
              "2": {"bird": "yes", "v0": "bird", "v1": "bird"}, "3": {"bird": "no", "v0": "not", "v1": "not"},
              "100": {"bird": "no", "v0": "not", "v1": None}, "101": {"bird": "yes", "v0": None, "v1": "bird"}}
    est = DC.estimate(rows, review, labels)
    # A: 40 frames, 1 in 4 a false positive for both -> 10 FP boxes of 40; v0 adds 1 FP box (O0), v1 a hit (O1).
    assert est["v0"]["fp_rate"] == pytest.approx(11 / 41)
    assert est["v1"]["fp_rate"] == pytest.approx(10 / 41)
    # Birds: 30 in A plus 1 in O1. v0 misses the O1 bird; v1 misses none.
    assert est["v0"]["fn_rate"] == pytest.approx(1 / 31)
    assert est["v1"]["fn_rate"] == pytest.approx(0.0)
    ci = DC.bootstrap(rows, review, labels, iters=200, seed=1)
    assert ci["v0"]["fp_rate"][0] <= est["v0"]["fp_rate"] <= ci["v0"]["fp_rate"][1]
    assert json.dumps(ci)                                      # serialisable


def test_script_has_no_db_write_statements():
    src = (DC._ROOT / "scripts/research/detector_compare_879.py").read_text(encoding="utf-8").upper()
    for verb in ("INSERT ", "UPDATE ", "DELETE ", "UPSERT", ".EXECUTE("):
        assert verb not in src
