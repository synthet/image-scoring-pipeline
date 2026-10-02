"""Scientific invariants for the human model selection study."""
import numpy as np
import pytest

from modules.score_analytics import study


def test_overlapping_groups_and_sessions_never_cross_splits():
    images = [
        {"id": 1, "session": "a"}, {"id": 2, "session": "b"},
        {"id": 3, "session": "c"}, {"id": 4, "session": "a"},
        {"id": 5, "session": "d"},
    ]
    groups = [{"image_ids": [1, 2]}, {"image_ids": [2, 3]}]
    components = study.connected_components(images, groups)
    assert len({components[i] for i in [1, 2, 3, 4]}) == 1
    assert components[5] != components[1]


def test_stratified_sample_has_known_inclusion_probabilities_and_is_reproducible():
    pool = [{"id": str(i), "stratum": "rare" if i < 5 else "common"} for i in range(100)]
    a = study.sample_strata(pool, 20, seed=7)
    assert a == study.sample_strata(list(reversed(pool)), 20, seed=7)
    assert len(a) == 20
    assert sum(r["weight"] for r in a) == pytest.approx(100)
    assert all(r["weight"] == pytest.approx(1 / r["inclusion_probability"]) for r in a)


def test_ties_credit_expected_random_choice_and_missing_frame_invalidates_group():
    result = study.group_metrics([0.5, 0.5, 0.1], [2, 1, 0], [True, False, False])
    assert result["top1"] == pytest.approx(0.5)
    assert result["pairwise"] == pytest.approx(5 / 6)
    assert result["reject_selected"] == 0
    assert study.group_metrics([0.5, np.nan, 0.1], [2, 1, 0], [True, False, False]) is None


def test_all_reject_groups_do_not_inflate_best_frame_accuracy():
    r = study.group_metrics([1.0, 0.0], [0, 0], [False, False])
    assert r["top1"] is None
    assert r["pairwise"] is None
    assert r["reject_selected"] == 1


def test_review_validation_rejects_model_labels_and_incomplete_grades():
    unit = {"id": "u", "kind": "stack", "image_ids": [1, 2]}
    record = {"unit_id": "u", "reviewer": "owner", "status": "done", "source": "human_blind",
              "frames": [{"image_id": 1, "grade": 2, "best": True}]}
    with pytest.raises(ValueError, match="every frame"):
        study.validate_review(unit, record)
    record["frames"].append({"image_id": 2, "grade": 0, "best": False})
    study.validate_review(unit, record)
    record["source"] = "auto"
    with pytest.raises(ValueError, match="human_blind"):
        study.validate_review(unit, record)


def test_blind_payload_does_not_expose_scores_strata_or_split():
    unit = {"id": "u", "kind": "single", "image_ids": [42], "stratum": "bad",
            "weight": 2, "split": "test", "repeat_of": "secret", "scores": {"liqe": 1}}
    assert study.blind_unit(unit) == {"id": "u", "kind": "single", "image_ids": [42]}


def test_unknown_timing_is_not_zero_cost_and_shared_dependencies_count_once():
    timings = {"encoder": 10, "a": 1, "b": 2}
    dependencies = {"a": ["encoder", "a"], "b": ["encoder", "b"]}
    assert study.inference_cost(["a", "b"], timings, dependencies) == 13
    assert study.inference_cost(["missing"], timings, dependencies) is None


def test_noninferiority_requires_paired_ci_not_nonsignificant_p_value():
    assert study.omission_decision([-0.01, 0.01], margin=0.02, independent=True) == "eligible"
    assert study.omission_decision([-0.08, 0.01], margin=0.02, independent=True) == "inconclusive"
    assert study.omission_decision([-0.01, 0.01], margin=0.02, independent=False) == "needs human labels"
