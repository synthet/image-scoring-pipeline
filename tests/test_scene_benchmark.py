"""Pure logic of the scene route benchmark (#412): pool, sweep, AC-4 choice, confusion weighting."""

from scripts.research.scene_route.scene_benchmark import (
    build_pool,
    choose_threshold,
    skip_sweep,
    weighted_confusion,
)


def _rows(n, folders):
    return [{"id": i, "file_path": f"/p/f{i % folders}/x{i}.nef"} for i in range(n)]


def test_pool_is_deterministic_excludes_prior_and_caps_folders():
    a = build_pool(_rows(100, 5), excluded={1, 2}, seed="s", size=50, per_folder=3)
    assert a == build_pool(_rows(100, 5), excluded={1, 2}, seed="s", size=50, per_folder=3)
    assert len(a) == 15  # 5 folders x 3
    assert not {1, 2} & {m["image_id"] for m in a}
    assert len(build_pool(_rows(100, 100), set(), "s", size=20, per_folder=3)) == 20


def test_skip_sweep_weights_and_counts():
    scored = [(0.01, True, 10.0), (0.5, True, 1.0), (0.2, False, 1.0), (0.01, False, 3.0)]
    row = skip_sweep(scored, [0.1])[0]
    assert row["bird_skipped"] == 1 and row["bird_n"] == 2
    assert row["bird_skip_rate"] == round(10 / 11, 4)
    assert row["other_run_rate"] == 0.25


def test_choose_threshold_takes_largest_within_ac4():
    sweep = [{"threshold": t, "bird_skip_rate": r} for t, r in ((0.1, 0.0), (0.2, 0.019), (0.3, 0.05))]
    assert choose_threshold(sweep)["threshold"] == 0.2
    assert choose_threshold([{"threshold": 0.1, "bird_skip_rate": 0.5}]) is None


def test_weighted_confusion_precision_and_recall():
    rows = [("wildlife_bird", "wildlife_bird", 3.0), ("wildlife_bird", "landscape", 1.0),
            ("landscape", "wildlife_bird", 1.0)]
    per = weighted_confusion(rows)["per_label"]
    assert per["wildlife_bird"] == {"precision": 0.75, "recall": 0.75}
    assert per["landscape"] == {"precision": 0.0, "recall": 0.0}
    assert per["people"] == {"precision": None, "recall": None}
