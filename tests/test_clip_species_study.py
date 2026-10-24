"""Decision and sampling invariants for the frozen CLIP species study."""

import numpy as np

from scripts.research.clip_species_study import decide, evaluate, select_sample


def test_shortlist_confidence_cannot_hide_a_better_outside_species():
    scores = np.array([0.32, 0.27, 0.11])
    broad = decide(scores, [0, 1, 2], confidence_floor=0.5)
    narrow = decide(scores, [1, 2], confidence_floor=0.5, outside_gap=0.02)
    assert broad["name_index"] == 0 and broad["accepted"]
    assert narrow["name_index"] == 1
    assert narrow["confidence"] > 0.5
    assert narrow["reason"] == "outside_list"


def test_no_bird_and_missing_species_count_as_errors_if_tagged():
    scores = np.array([[0.30, 0.10], [0.30, 0.10], [0.10, 0.30]])
    truth = ["no_bird", "species_b", "species_b"]
    result = evaluate(scores, truth, ["species_a", "species_b"], [0, 1], confidence_floor=0.5)
    assert result["n_evaluable"] == 3
    assert result["correct_tags"] == 1
    assert result["wrong_tags"] == 2


def test_sample_is_deterministic_and_keeps_presence_controls():
    rows = [{"image_id": i, "presence": "bird" if i < 20 else "no_bird"} for i in range(30)]
    hard = {1, 3, 5, 7, 9}
    a = select_sample(rows, hard, bird_count=8, no_bird_count=4, hard_count=3, seed=12)
    b = select_sample(list(reversed(rows)), hard, bird_count=8, no_bird_count=4, hard_count=3, seed=12)
    assert a == b
    assert len(a) == 15
    assert sum(r["reason"] == "no_bird_control" for r in a) == 4
    assert sum(r["reason"] == "hard_bird" for r in a) == 3
