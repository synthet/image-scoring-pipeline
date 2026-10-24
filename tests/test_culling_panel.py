"""Pure-function tests for the #415 culling panel harness (no DB, no CLIs)."""

import json

from scripts.research.judges.culling_panel import (
    NONE,
    compare,
    crop_region,
    group_consensus,
    parse_reply,
    weighted_kappa,
)


def _reply(grades, best, skip=False):
    frames = [{"id": f"F{i}", "grade": g, "best": f"F{i}" == best, "reason": "r"} for i, g in enumerate(grades, 1)]
    return json.dumps({"skip": skip, "skip_reason": "", "frames": frames})


def test_parse_reply_accepts_valid_and_all_reject():
    assert parse_reply("noise " + _reply([2, 1, 0], "F1"), 3)["best"] == "F1"
    assert parse_reply(_reply([0, 0], None), 2)["best"] == NONE


def test_parse_reply_rejects_rubric_violations():
    assert parse_reply(_reply([1, 1], "F1"), 2) is None  # best must be a pick
    assert parse_reply(_reply([2, 0], None), 2) is None  # a pick but no best
    assert parse_reply(_reply([2, 0], "F1"), 3) is None  # missing frame
    two_best = json.dumps({"skip": False, "frames": [
        {"id": "F1", "grade": 2, "best": True}, {"id": "F2", "grade": 2, "best": True}]})
    assert parse_reply(two_best, 2) is None


def test_parse_reply_skip():
    assert parse_reply(json.dumps({"skip": True, "skip_reason": "identical"}), 2)["skip"] is True


def test_group_consensus_quorum_and_splits():
    replies = [parse_reply(_reply(g, b), 3) for g, b in (
        ([2, 1, 0], "F1"), ([2, 1, 0], "F1"), ([2, 0, 0], "F1"), ([1, 2, 0], "F2"))]
    c = group_consensus(3, replies, need=3)
    assert c["best"] == "F1"
    assert c["grades"] == {"F1": 2, "F2": None, "F3": 0}
    assert c["grade_splits"] == ["F2"]


def test_group_consensus_missing_reply_keeps_quorum():
    replies = [parse_reply(_reply([2, 0], "F1"), 2)] * 2 + [None, None]
    c = group_consensus(2, replies, need=3)
    assert c["best"] is None and c["grade_splits"] == ["F1", "F2"]


def test_weighted_kappa_perfect_and_none():
    assert weighted_kappa([(0, 0), (1, 1), (2, 2)]) == 1.0
    assert weighted_kappa([]) is None


def test_compare_counts_best_grades_and_pairs():
    owner = {1: {"grades": {10: 2, 11: 0}, "best": 10}, 2: {"grades": {20: 0, 21: 0}, "best": NONE}}
    panel = {1: {"grades": {10: 2, 11: 1}, "best": 10}, 2: {"grades": {20: 0, 21: None}, "best": None}}
    r = compare(owner, panel)
    assert (r["best_agree"], r["best_n"]) == (1, 1)
    assert r["frames"] == 3 and r["pairs"] == 1 and r["pair_order_agree"] == 1.0


def test_crop_region_native_window_on_subject():
    # small subject: window is CROP_SIDE native px, centred on the union of the boxes
    assert crop_region([(0.40, 0.40, 0.42, 0.43), (0.41, 0.41, 0.44, 0.44)], 8256, 5504) == (2827, 1671, 4107, 2951)
    # no boxes: frame centre
    assert crop_region([], 8256, 5504) == (3488, 2112, 4768, 3392)
    # large subject: capped at 2 * CROP_SIDE around the union centre
    assert crop_region([(0.0, 0.0, 0.9, 0.9)], 8256, 5504) == (2435, 1196, 4995, 3756)
    # window pushed back inside the frame at an edge
    assert crop_region([(0.95, 0.95, 0.99, 0.99)], 8256, 5504) == (6976, 4224, 8256, 5504)
