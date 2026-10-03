"""Pure-logic guards for the #472 scene-route re-gate: decision, grid, selection."""

from scripts.research.detector_benchmark.v1_promotion_gate import RuleParams
from scripts.research.detector_benchmark.v1_regate import (
    RegateParams,
    combine,
    grid,
    regate,
    select,
)

SNAP = {"regions": [{"region_id": 10, "rank": 0, "conf": 0.9, "region": [0.1, 0.1, 0.3, 0.3]},
                    {"region_id": 11, "rank": 1, "conf": 0.5, "region": [0.6, 0.6, 0.62, 0.62]}]}
FROZEN = RuleParams("rtmdet_only", 0.55, 0.5, "rtmdet")
PROBE = {"coco": [{"region": [0.5, 0.5, 0.9, 0.9], "conf": 0.8, "cls": "bird"}], "refine": []}


def test_grid_is_the_predeclared_78():
    g = grid()
    assert len(g) == 78 == len({p.rule_hash() for p in g})
    assert min(p.threshold for p in g) == 0.03 and max(p.threshold for p in g) == 0.15


def test_scene_gate_and_missing_label():
    p = RegateParams(0.065, "none", 0.0)
    assert regate(SNAP, PROBE, None, p, FROZEN).reason == "no_scene_label"
    assert regate(SNAP, PROBE, 0.05, p, FROZEN).reason == "scene_not_bird"
    d = regate(SNAP, PROBE, 0.07, p, FROZEN)
    assert d.action == "promote" and d.primary == (0.1, 0.1, 0.3, 0.3) and d.source == "v1:bird"


def test_rtmdet_corroboration_uses_frozen_geometry():
    p = RegateParams(0.03, "rtmdet", 0.0)
    d = regate(SNAP, PROBE, 0.5, p, FROZEN)
    assert d.action == "promote" and d.primary == (0.5, 0.5, 0.9, 0.9)
    weak = {"coco": [{"region": [0.5, 0.5, 0.9, 0.9], "conf": 0.3, "cls": "bird"}], "refine": []}
    assert regate(SNAP, weak, 0.5, p, FROZEN).reason == "no_rtmdet_corroboration"
    assert regate(SNAP, None, 0.5, p, FROZEN).reason == "unprobed"


def test_min_area_keeps_small_boxes_in_shadow():
    small = {"regions": [{"region_id": 1, "rank": 0, "conf": 0.9, "region": [0.1, 0.1, 0.15, 0.15]}]}
    assert regate(small, None, 0.5, RegateParams(0.03, "none", 0.005), FROZEN).reason == "box_too_small"
    assert regate(small, None, 0.5, RegateParams(0.03, "none", 0.0), FROZEN).action == "promote"


def _design(promoted, usable, prec):
    return {"promoted": promoted, "usable": usable, "weighted_precision": prec,
            "est_promoted": promoted * 100.0, "est_usable": usable * 100.0}


def test_eligibility_needs_both_designs():
    p = RegateParams(0.05, "none", 0.0)
    assert combine(p, _design(20, 19, 0.95), _design(20, 19, 0.95), 6820)["eligible"]
    assert not combine(p, _design(20, 19, 0.99), _design(20, 16, 0.84), 6820)["eligible"]   # one design < 0.85
    assert not combine(p, _design(20, 19, 0.95), _design(9, 9, 1.0), 6820)["eligible"]     # < 10 promoted


def test_select_prefers_more_usable_then_higher_threshold():
    a = combine(RegateParams(0.05, "none", 0.0), _design(20, 19, 0.95), _design(20, 19, 0.95), 6820)
    b = combine(RegateParams(0.10, "none", 0.0), _design(20, 19, 0.95), _design(20, 19, 0.95), 6820)
    c = combine(RegateParams(0.03, "none", 0.0), _design(30, 28, 0.93), _design(30, 28, 0.93), 6820)
    assert select([a, b, c])["rule_hash"] == c["rule_hash"]
    assert select([a, b])["rule_hash"] == b["rule_hash"]
    assert select([]) is None


# --------------------------------------------------------------------------- #
# v1_regate_rule/2 (option b)
# --------------------------------------------------------------------------- #
from scripts.research.detector_benchmark.v1_regate import SubsetParams, grid_b, select_b  # noqa: E402


def _probe_birds(*confs):
    return {"coco": [{"region": [0.1 + 0.2 * n, 0.1, 0.2 + 0.2 * n, 0.3], "conf": c, "cls": "bird"}
                     for n, c in enumerate(confs)], "refine": []}


def test_grid_b_is_the_predeclared_60():
    g = grid_b()
    assert len(g) == 60 == len({p.rule_hash() for p in g})


def test_subset_bird_count_conf_and_scene():
    p = SubsetParams(0.70, 2, 0.50)
    assert p.decide(SNAP, _probe_birds(0.8), 0.4).reason == "scene_not_bird"
    assert p.decide(SNAP, _probe_birds(0.8, 0.3, 0.3), 0.9).reason == "too_many_birds"
    assert p.decide(SNAP, _probe_birds(0.8, 0.2, 0.2), 0.9).action == "promote"   # conf < 0.25 not counted
    assert p.decide(SNAP, _probe_birds(0.65), 0.9).reason == "rtmdet_below_conf"
    assert SubsetParams(0.55, None, 0.05).decide(SNAP, _probe_birds(*[0.6] * 9), 0.9).action == "promote"


def test_select_b_tie_breaks():
    def res(c, k, t, usable=100, promoted=100):
        p = SubsetParams(c, k, t)
        return {"eligible": True, "params": {"min_rt_conf": c, "max_rt_birds": k, "threshold": t},
                "rule_hash": p.rule_hash(), "est_usable": usable, "est_promoted": promoted}
    a, b, c = res(0.55, None, 0.05), res(0.70, None, 0.05), res(0.70, 1, 0.05)
    assert select_b([a, b, c])["rule_hash"] == c["rule_hash"]
    assert select_b([a, res(0.55, 2, 0.5, usable=120, promoted=125)])["params"]["max_rt_birds"] == 2


def test_rule_c_is_rule_b_on_scene_v3():
    from modules.scene_route import SceneClassifier
    from scripts.research.detector_benchmark.v1_regate import SubsetParamsV3

    b, c = SubsetParams(0.55, 3, 0.5), SubsetParamsV3(0.55, 3, 0.5)
    assert b.rule_hash() != c.rule_hash()
    assert c.decide(SNAP, _probe_birds(0.8), 0.9).action == b.decide(SNAP, _probe_birds(0.8), 0.9).action == "promote"
    assert SubsetParamsV3.SCENE_VERSION == SceneClassifier("siglip2_base", prompt_set="scene_v3").version
    assert len(grid_b(SubsetParamsV3)) == 60
