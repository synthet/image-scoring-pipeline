"""Pure logic of the agent-panel harnesses (#592, #593, #408): parsing, votes, consensus, gate."""

import json

from scripts.research.judges import box_panel as bp
from scripts.research.judges import species_panel as sp


def test_candidates_dedupe_and_fall_back_to_lower_ranks():
    row = {"old": "Carolina Wren", "new_top": "carolina wren", "new_top3": [["Carolina Wren", 0.9], ["Bewick's Wren", 0.05]]}
    assert sp.candidates(row) == ["Carolina Wren", "Bewick's Wren"]
    assert sp.candidates({"old": None, "new_top": "Osprey", "new_top3": [["Osprey", 0.4], ["Bald Eagle", 0.3]]}) == [
        "Osprey", "Bald Eagle"]


def test_parse_reply_takes_last_json_and_ignores_bad_rows():
    text = 'thinking {"x": 1}\n{"images":[{"id":"ab","own_id":"Osprey","choice":"a"},{"id":"cd","choice":"maybe"}]}'
    assert sp.parse_reply(text) == {"ab": {"own_id": "Osprey", "choice": "A"}}


def test_votes_and_consensus():
    f = {"A": "Carolina Wren", "B": "House Wren"}
    a = {"choice": "A", "own_id": "Carolina Wren"}
    neither_known = {"choice": "NEITHER", "own_id": "Bewick's Wren"}
    neither_vague = {"choice": "NEITHER", "own_id": ""}
    assert sp.vote(f, a) == "carolinawren"
    assert sp.vote(f, neither_known) == "bewickswren"
    assert sp.vote(f, neither_vague) == sp.OTHER
    assert sp.vote(f, {"choice": "UNSURE", "own_id": ""}) is None
    assert sp.consensus_label(f, [a, a, a, neither_known], need=3) == "carolinawren"
    # Three judges reject both names but disagree on the species: both candidates are wrong.
    assert sp.consensus_label(f, [neither_known, neither_vague, {"choice": "NEITHER", "own_id": "Wrentit"}, a],
                              need=3) == sp.OTHER
    assert sp.consensus_label(f, [a, a, neither_known, None], need=3) is None


def test_leak_check_flags_group_words():
    assert sp.leaks("A small brown bird like a wren", ["Carolina Wren", "Osprey"]) == ["wren"]
    assert sp.leaks("Rusty upperparts, white eyebrow", ["Carolina Wren"]) == []


def test_gate_weights_strata_to_the_cohort(tmp_path):
    full = {"images": [{"image_id": i, "outcome": "changed", "old": "X", "new": "Y"} for i in range(1, 11)]
            + [{"image_id": i, "outcome": "same", "old": "Y", "new": "Y"} for i in range(11, 31)]}
    frames = [{"token": f"t{i}", "image_id": i, "stratum": "changed"} for i in (1, 2)]
    frames += [{"token": f"t{i}", "image_id": i, "stratum": "same"} for i in (11, 12)]
    (tmp_path / "manifest.json").write_text(json.dumps({"frames": frames}))
    labels = {"t1": "y", "t2": "y", "t11": "y", "t12": "y"}
    (tmp_path / "consensus.json").write_text(json.dumps({"labels": labels}))
    (tmp_path / "full.json").write_text(json.dumps(full))
    res = sp.gate(tmp_path, tmp_path / "full.json", None)
    # changed: new right on both, weight 10/2; same: old and new right on both, weight 20/2.
    assert res["weighted"] == {"old_right": 20.0, "old_wrong": 10.0, "new_right": 30.0, "new_wrong": 0.0}
    assert res["G5a"]["pass"] and res["G5b"]["pass"]


def test_box_verdicts_and_parse():
    reply = '{"images":[{"id":"a","presence":"bird","grade":"usable"},{"id":"b","presence":"no_bird","grade":"x"},'\
            '{"id":"c","presence":"bird","grade":"wrong_target"}]}'
    got = bp.parse_reply(reply, "usable")
    assert set(got) == {"a", "c"}  # 'b' has an unknown grade
    assert bp.verdict(got["a"], "usable") == "usable"
    assert bp.verdict(got["c"], "usable") == "not_usable"
    assert bp.verdict({"presence": "no_bird", "grade": "unsure"}, "usable") == "not_usable"
    assert bp.verdict({"presence": "unsure", "grade": "unsure"}, "usable") is None
    tight = bp.parse_reply('{"images":[{"id":"a","grade":"tight"}]}', "tight")
    assert bp.verdict(tight["a"], "tight") == "TIGHT"


def test_rule4_small_boxes_need_scene_and_single_bird():
    class D:
        def __init__(self, primary):
            self.action, self.primary = "promote", primary

    small, large = D((0.1, 0.1, 0.15, 0.15)), D((0.1, 0.1, 0.5, 0.5))
    one = [{"cls": "bird", "conf": 0.6}]
    two = one + [{"cls": "bird", "conf": 0.3}]
    assert bp.rule4_promotes(large, two, 0.6)
    assert bp.rule4_promotes(small, one, 0.96)
    assert not bp.rule4_promotes(small, two, 0.99)
    assert not bp.rule4_promotes(small, one, 0.9)


def test_cascade_box_mirrors_production_combination():
    yolo = {"yolo": [{"region": [0.1, 0.1, 0.3, 0.3], "conf": 0.5}], "coco": [], "refine": []}
    assert bp.cascade_box(yolo) == ("yolo", [0.1, 0.1, 0.3, 0.3])
    weak = {"yolo": [], "coco": [{"region": [0.4, 0.4, 0.6, 0.6], "conf": 0.5, "cls": "bird"}], "refine": []}
    assert bp.cascade_box(weak) is None  # below the 0.60 fallback threshold
    small = [0.40, 0.40, 0.45, 0.45]
    rec = {"yolo": [], "coco": [{"region": small, "conf": 0.7, "cls": "bird"}],
           "refine": [{"coco_region": small, "yolo": [{"region": [0.401, 0.401, 0.449, 0.449], "conf": 0.6}]}]}
    assert bp.cascade_box(rec) == ("coco+refine", [0.401, 0.401, 0.449, 0.449])
