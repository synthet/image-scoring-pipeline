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


def test_imagenet_groups_sum_to_one_and_hit_bird_ranges():
    from scripts.research.scene_route.scene_benchmark import IMAGENET_GROUPS, imagenet_groups

    probs = [0.0] * 1000
    probs[130] = 0.6  # flamingo
    probs[150] = 0.1  # sea lion
    probs[310] = 0.1  # ant
    probs[500] = 0.2  # a non-animal class
    g = imagenet_groups(probs)
    assert g == {"wildlife_bird": 0.6, "wildlife_insect": 0.1, "other_animal": 0.1, "non_animal": 0.2}
    flat = [i for idx in IMAGENET_GROUPS.values() for i in idx]
    assert len(flat) == len(set(flat))  # groups never overlap


def test_arm_view_scores_bird_and_any_animal():
    from scripts.research.scene_route.scene_benchmark import arm_view

    rec = {"hf_clip_b32": {"top_label": "landscape", "probs": {"wildlife_bird": 0.2, "other_animal": 0.1,
                                                                "landscape": 0.7},
                           "cosines": {"wildlife_bird": 0.25}},
           "imagenet_convnext": {"probs": {"wildlife_bird": 0.5, "other_animal": 0.1, "wildlife_insect": 0.0,
                                           "non_animal": 0.4}}}
    top, scores = arm_view(rec, "hf_clip_b32")
    assert top == "landscape" and scores["prob"] == 0.2 and abs(scores["animal_prob"] - 0.3) < 1e-9
    assert scores["cosine"] == 0.25
    top, scores = arm_view(rec, "imagenet_convnext")
    assert top is None and set(scores) == {"prob", "animal_prob"}


def test_probe_is_out_of_fold_by_folder():
    import numpy as np

    from scripts.research.scene_route.scene_benchmark import probe_predictions

    rng = np.random.default_rng(0)
    emb, labels, folders = {}, {}, {}
    for i in range(60):
        lab = "wildlife_bird" if i % 2 else "landscape"
        emb[i] = list(rng.normal(size=4) + (3 if lab == "wildlife_bird" else -3))
        labels[i] = "cant_tell" if i == 7 else lab
        folders[i] = f"f{i % 10}"
    out = probe_predictions(emb, labels, folders)
    assert set(out) == set(emb)  # cant_tell is still predicted
    correct = sum(out[i]["top_label"] == labels[i] for i in emb if labels[i] != "cant_tell")
    assert correct >= 55
