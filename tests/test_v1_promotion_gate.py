"""Pure-logic guards for the bird v1 promotion gate (#469): rule, sampler, interval, matching."""

from scripts.research.detector_benchmark.v1_promotion_gate import (
    Decision,
    RuleParams,
    area_band,
    conf_band,
    decide,
    outcome_for,
    rule_grid,
    sample_strata,
    select,
    validation_population,
    wilson,
)

V1 = [{"region_id": 10, "rank": 0, "conf": 0.9, "region": (0.1, 0.1, 0.3, 0.3)},
      {"region_id": 11, "rank": 1, "conf": 0.5, "region": (0.6, 0.6, 0.8, 0.8)}]
OVERLAP_V1 = RuleParams("overlap", 0.4, 0.5, "v1")


def _coco(region, conf=0.8, cls="bird"):
    return {"region": region, "conf": conf, "cls": cls}


def test_only_rtmdet_bird_class_corroborates():
    dog = [_coco((0.1, 0.1, 0.3, 0.3), cls="dog")]
    assert decide(V1, dog, [], OVERLAP_V1) == Decision("keep_shadow", "no_rtmdet_bird")
    low = [_coco((0.1, 0.1, 0.3, 0.3), conf=0.3)]
    assert decide(V1, low, [], OVERLAP_V1).action == "keep_shadow"


def test_overlap_threshold_and_primary_choice():
    far = [_coco((0.4, 0.4, 0.5, 0.5))]
    assert decide(V1, far, [], OVERLAP_V1).reason == "no_rtmdet_bird_overlap"
    # Only the rank-1 v1 box is corroborated: it becomes the primary.
    d = decide(V1, [_coco((0.6, 0.6, 0.8, 0.81))], [], OVERLAP_V1)
    assert (d.action, d.v1_region_id, d.primary, d.source) == ("promote", 11, (0.6, 0.6, 0.8, 0.8), "v1:bird")


def test_lowest_v1_rank_wins_when_both_corroborated():
    coco = [_coco((0.6, 0.6, 0.8, 0.8), conf=0.95), _coco((0.1, 0.1, 0.3, 0.3), conf=0.5)]
    assert decide(V1, coco, [], OVERLAP_V1).v1_region_id == 10


def test_rtmdet_primary_uses_refine_geometry_when_it_overlaps():
    coco_region = (0.1, 0.1, 0.12, 0.12)
    v1 = [{"region_id": 1, "rank": 0, "conf": 0.9, "region": (0.1, 0.1, 0.12, 0.12)}]
    refine = [{"coco_region": coco_region, "yolo": [{"region": (0.101, 0.1, 0.12, 0.121), "conf": 0.7}]}]
    d = decide(v1, [_coco(coco_region)], refine, RuleParams("overlap", 0.4, 0.5, "rtmdet"))
    assert d.source == "coco+refine:bird" and d.primary == (0.101, 0.1, 0.12, 0.121)
    d = decide(v1, [_coco(coco_region)], [], RuleParams("overlap", 0.4, 0.5, "rtmdet"))
    assert d.source == "coco:bird" and d.primary == coco_region


def test_rtmdet_only_promotes_without_v1_overlap():
    d = decide(V1, [_coco((0.4, 0.4, 0.5, 0.5))], [], RuleParams("rtmdet_only", 0.4, 0.5, "rtmdet"))
    assert d.action == "promote" and d.v1_region_id is None


def test_rule_hash_is_stable_and_distinct():
    hashes = [p.rule_hash() for p in rule_grid()]
    assert len(set(hashes)) == len(hashes)
    assert RuleParams("overlap", 0.4, 0.5, "v1").rule_hash() == OVERLAP_V1.rule_hash()


def test_outcome_matches_graded_boxes_by_iou():
    label = {"presence": "bird", "graded": [((0.1, 0.1, 0.3, 0.3), "usable", "v1 primary")]}
    assert outcome_for(label, Decision("promote", "x", (0.1, 0.1, 0.3, 0.31))) == "usable"
    assert outcome_for(label, Decision("promote", "x", (0.6, 0.6, 0.8, 0.8))) == "ungraded"
    assert outcome_for({"presence": "no_bird", "graded": []}, Decision("promote", "x", (0, 0, 1, 1))) == "no_bird"


def test_select_respects_precision_floor_and_prefers_conservative_ties():
    def r(conf, promoted, usable):
        # Dev counts stay small; the weighted estimates (x100) drive selection.
        return {"params": {"min_coco_conf": conf, "min_iou": 0.5}, "promoted": 20, "usable": 15,
                "est_promoted": promoted * 100, "est_usable": usable * 100,
                "weighted_precision": usable / promoted, "rule_hash": str(conf)}
    assert select([r(0.25, 40, 30)]) is None
    assert select([r(0.25, 20, 19), r(0.40, 20, 19)])["params"]["min_coco_conf"] == 0.40
    assert select([r(0.25, 30, 28), r(0.40, 20, 19)])["est_usable"] == 2800


def test_sampler_is_deterministic_and_caps_folders():
    pop = {"promote_small": [{"image_id": i, "folder": f"f{i % 3}"} for i in range(30)]}
    a = sample_strata(pop, "s1", {"promote_small": 10})
    assert a == sample_strata(pop, "s1", {"promote_small": 10})
    assert sorted(m["folder"] for m in a["promote_small"]) == ["f0", "f1", "f2"]  # one per folder
    wide = {"promote_small": [{"image_id": i, "folder": f"f{i}"} for i in range(30)]}
    assert len(sample_strata(wide, "s1", {"promote_small": 10})["promote_small"]) == 10


def test_validation_population_excludes_dev_images_and_folders():
    snap = {i: {"file_path": f"/p/{'dev' if i == 2 else 'f' + str(i)}/x{i}.nef", "regions": [
        {"region_id": i, "rank": 0, "conf": 0.9, "region": [0.1, 0.1, 0.3, 0.3]}]} for i in range(1, 5)}
    prod = {i: {"coco": [_coco((0.1, 0.1, 0.3, 0.3))], "refine": []} for i in (1, 2, 3)}
    prod[4] = {"error": "rendition_mismatch"}
    pop, excluded = validation_population(snap, prod, OVERLAP_V1, dev_ids={1}, dev_folders={"/p/dev"})
    assert excluded == {"dev_image": 1, "dev_folder": 1, "probe_error": 1}
    assert [m["image_id"] for m in pop["promote_large"]] == [3]


def test_bands_and_wilson():
    assert [conf_band(c) for c in (0.39, 0.4, 0.69, 0.7)] == ["low", "mid", "mid", "high"]
    assert [area_band((0, 0, a, 1)) for a in (0.004, 0.005, 0.019, 0.02)] == ["small", "medium", "medium", "large"]
    lo, hi = wilson(57, 60)
    assert 0.85 < lo < 0.87 and 0.98 < hi < 0.99
    assert wilson(0, 0) == (0.0, 1.0)
