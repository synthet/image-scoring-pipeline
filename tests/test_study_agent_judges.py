"""CLI-agent rater stream for the blind study (#517): blind prompts, strict parsing, consensus."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research.model_selection import study_agent_judges as saj

UNIT = {"id": "abc123", "kind": "burst", "split": "train", "image_ids": [901, 902, 903]}


def _reply(frames):
    return "thinking...\n" + json.dumps({"units": [{"unit": "abc123", "frames": frames}]})


def _frames(*rows):
    return [{"frame": n, "grade": g, "best": b} for n, (g, b) in enumerate(rows, 1)]


def test_group_units_excludes_singles_test_split_and_repeats():
    sample = {"units": [
        UNIT,
        {**UNIT, "id": "t", "split": "test"},
        {**UNIT, "id": "s", "kind": "single", "image_ids": [1]},
        {**UNIT, "id": "r", "repeat_of": "abc123"},
        {**UNIT, "id": "v", "kind": "stack", "split": "validation"},
    ]}
    assert [u["id"] for u in saj.group_units(sample)] == ["abc123", "v"]


def test_prompt_is_blind():
    prompt = saj.prompt_for([UNIT], Path("root"), "claude")
    assert "abc123_1.jpg" in prompt and "frame 3" in prompt
    for leak in ("901", "image_id", "train", "split", "score", "stratum"):
        assert leak not in prompt


def test_batches_pack_whole_units_within_frame_budget():
    units = [{**UNIT, "id": f"u{k}", "image_ids": list(range(n))} for k, n in enumerate([2, 3, 12, 5, 4, 7])]
    out = saj.batches(units, max_frames=12)
    assert sorted(u["id"] for b in out for u in b) == sorted(u["id"] for u in units)
    assert all(sum(len(u["image_ids"]) for u in b) <= 12 for b in out)
    assert out == saj.batches(list(reversed(units)), max_frames=12)  # seeded, input-order independent


def test_valid_reply_becomes_a_review_shaped_record():
    reply = saj.parse_reply(_reply(_frames(("pick", True), ("keep", False), ("reject", False))))
    rec = saj.to_record(UNIT, reply["abc123"])
    assert [(f["image_id"], f["grade"], f["best"]) for f in rec["frames"]] == [(901, 2, True), (902, 1, False),
                                                                               (903, 0, False)]


@pytest.mark.parametrize("frames", [
    _frames(("pick", True), ("keep", False)),                      # missing frame
    _frames(("keep", True), ("keep", False), ("reject", False)),    # best is not a pick
    _frames(("pick", False), ("keep", False), ("reject", False)),   # usable frames but no best
    _frames(("great", True), ("keep", False), ("reject", False)),   # unknown grade
    [{"frame": 1, "grade": "pick", "best": "yes"}, {"frame": 2, "grade": "keep", "best": False},
     {"frame": 3, "grade": "reject", "best": False}],               # non-boolean best
])
def test_invalid_replies_are_never_coerced(frames):
    assert saj.to_record(UNIT, frames) is None


def _rec(*rows):
    return {"frames": [{"image_id": 900 + n, "grade": g, "best": b} for n, (g, b) in enumerate(rows, 1)]}


def test_consensus_majority_grade_and_most_starred_pick():
    a = _rec((2, True), (2, False), (0, False))
    b = _rec((2, False), (2, True), (1, False))
    c = _rec((2, True), (1, False), (0, False))
    out = saj.consensus([a, b, c])
    assert [(f["grade"], f["best"]) for f in out["frames"]] == [(2, True), (2, False), (0, False)]


def test_consensus_keeps_star_ties_and_needs_two_judges():
    a = _rec((2, True), (2, False))
    b = _rec((2, False), (2, True))
    assert [f["best"] for f in saj.consensus([a, b])["frames"]] == [True, True]
    assert saj.consensus([a]) is None


def test_consensus_without_any_pick_is_invalid_unless_all_rejected():
    a = _rec((2, True), (1, False))
    b = _rec((1, False), (1, False))  # lower median of {2,1} is 1 -> keeps but no pick
    assert saj.consensus([a, b]) is None
    rejected = saj.consensus([_rec((0, False), (0, False)), _rec((0, False), (0, False))])
    assert not any(f["best"] for f in rejected["frames"])


def test_agreement_aligns_frames_by_image_id():
    a = _rec((2, True), (0, False))
    b = {"frames": list(reversed(_rec((2, True), (1, False))["frames"]))}
    assert saj.agreement(a, b) == {"frames": 2, "same_grade": 1, "best_overlap": True}
