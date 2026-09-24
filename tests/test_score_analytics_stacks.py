"""Unit tests for modules.score_analytics.stacks (within-stack culling signals)."""

import numpy as np
import pytest

from modules.score_analytics import stacks


def _fixture():
    # 3 stacks × 4 images + 2 unstacked images. Picks: first image of each stack.
    stack_ids = np.array([1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 0, 0])
    pick_status = np.array([1, 0, 0, -1, 1, 0, 0, -1, 1, 0, 0, -1, 0, 0], dtype=np.int8)
    image_ids = np.arange(1, 15)
    rng = np.random.default_rng(1)
    good = np.array([0.9, 0.6, 0.5, 0.1, 0.8, 0.5, 0.4, 0.2, 0.7, 0.4, 0.3, 0.05, 0.5, 0.5])
    scene = np.repeat([0.2, 0.5, 0.8, 0.5], [4, 4, 4, 2]).astype(float)
    noise = rng.random(14)
    partial = good.copy()
    partial[[1, 2, 3]] = np.nan  # stack 1 has a single scored image -> excluded
    series = {"good": good, "scene": scene, "noise": noise, "partial": partial}
    return series, list(series), stack_ids, pick_status, image_ids


def test_analyze_stacks_signals():
    series, keys, stack_ids, picks, ids = _fixture()
    res = stacks.analyze_stacks(series, keys, stack_ids, picks, ids, {1: 1, 2: 6}, per_stack=True)

    assert res["stacks_considered"] == 3
    assert res["images_in_stacks"] == 12
    assert res["stacks_with_picks"] == 3
    m = {x["dimension"]: x for x in res["models"]}

    assert m["good"]["pick_auc"] == pytest.approx(1.0)
    assert m["good"]["reject_auc"] == pytest.approx(1.0)
    assert m["good"]["pick_top1_rate"] == pytest.approx(1.0)
    assert m["good"]["best_match_rate"] == pytest.approx(0.5)  # stack 1 best=1 (hit), stack 2 best=6 (miss)
    assert m["good"]["pick_pairs"] == 9

    assert m["scene"]["pick_auc"] == pytest.approx(0.5)
    assert m["scene"]["within_share"] == pytest.approx(0.0)
    assert m["scene"]["tie_rate"] == pytest.approx(1.0)
    assert m["scene"]["within_std_mean"] == pytest.approx(0.0)

    assert m["partial"]["stacks"] == 2
    assert res["ranking"][0] in ("good", "partial")
    assert res["ranking"][-1] in ("scene", "noise")

    agree = res["agreement"]["spearman"]
    gi = keys.index("good")
    assert agree[gi][gi] == pytest.approx(1.0)
    assert res["agreement"]["stacks"][gi][keys.index("partial")] == 2

    rows = [r for r in res["per_stack"] if r["dimension"] == "good"]
    assert len(rows) == 3
    assert rows[0]["top1_image_id"] == 1 and rows[0]["top1_is_pick"] is True
    assert rows[0]["top_gap"] == pytest.approx(0.3)


def test_analyze_stacks_min_size_and_empty():
    series, keys, stack_ids, picks, ids = _fixture()
    assert stacks.analyze_stacks(series, keys, stack_ids, picks, ids, min_size=5)["stacks_considered"] == 0
    none = stacks.analyze_stacks(series, keys, np.zeros(14, dtype=int), picks, ids)
    assert none["stacks_considered"] == 0
    assert all(x["pick_auc"] is None for x in none["models"])


def test_rank_average_ties():
    assert stacks._rank(np.array([0.3, 0.1, 0.3, 0.2])).tolist() == [2.5, 0.0, 2.5, 1.0]
