"""#694 rubric amendment (revision 2): control candidates, blind review rounds and the lock. Synthetic labels only."""
import json

import pytest
from PIL import Image

from scripts.research.detector_benchmark import promotion_694_controls as controls

SEED = "test-controls"
ORDER_SEED = "test-review-order"


def labels():
    rows = [{"image_id": str(i), "box_label": "wrong_target"} for i in range(1, 9)]
    rows += [{"image_id": str(i), "box_label": "poor_crop"} for i in range(100, 127)]
    rows += [{"image_id": str(i), "box_label": "usable"} for i in range(200, 229)]
    return rows + [{"image_id": "300", "box_label": "unsure"}]


def keys():
    wrong = {f"w{i}": {"image_id": i, "grade": "wrong_target", "usable": False} for i in range(1, 9)}
    first = {**wrong, **{f"a{i}": {"image_id": i, "grade": "poor_crop", "usable": False} for i in range(100, 106)},
             **{f"b{i}": {"image_id": i, "grade": "usable", "usable": True} for i in range(200, 206)}}
    second = {**wrong, **{f"c{i}": {"image_id": i, "grade": "poor_crop", "usable": False} for i in range(106, 112)},
              **{f"d{i}": {"image_id": i, "grade": "usable", "usable": True} for i in range(206, 212)}}
    return [first, second]


def candidates():
    strata = controls.candidate_lists(labels(), keys(), {"126", "228"}, SEED)
    return {"seed": SEED, "review_order_seed": ORDER_SEED, "strata": strata}


def stored():
    return {r["image_id"]: r["box_label"] for r in labels()}


def review(round_number, items, wrong=()):
    rows = []
    for item in items:
        label = stored()[str(item["image_id"])]
        blind = "unsure" if item["image_id"] in wrong else label
        rows.append({**item, "round": round_number, "blind": blind, "stored": label,
                     "decision": controls.decide(blind, label)})
    return rows


def test_exclusion_rule_drops_the_24_earlier_frames_and_reuses_the_8_wrong_target():
    strata = candidates()["strata"]
    assert sorted(strata["wrong_target"]) == list(range(1, 9))
    assert set(range(100, 112)).isdisjoint(strata["poor_crop"])
    assert set(range(200, 212)).isdisjoint(strata["usable"])
    assert (len(strata["poor_crop"]), len(strata["usable"])) == (14, 16)  # frozen-sample ids 126 and 228 dropped
    assert 300 not in sum(strata.values(), [])


def test_wrong_target_frames_must_match_between_draws():
    first, second = keys()
    second["w1"] = {"image_id": 999, "grade": "wrong_target", "usable": False}
    with pytest.raises(ValueError, match="wrong_target"):
        controls.candidate_lists(labels(), [first, second], set(), SEED)


def test_candidate_order_is_the_same_on_every_run():
    assert controls.candidate_lists(labels(), keys(), set(), SEED) == controls.candidate_lists(
        list(reversed(labels())), keys(), set(), SEED)
    assert controls.candidate_lists(labels(), keys(), set(), SEED) != controls.candidate_lists(
        labels(), keys(), set(), "other-seed")


def test_first_round_is_8_6_6_in_mixed_order_without_hints():
    first = controls.replay(candidates(), [], stored())["next_round"]
    assert [r["stratum"] for r in first].count("wrong_target") == 8
    assert {s: [r["stratum"] for r in first].count(s) for s in controls.COMPOSITION} == controls.COMPOSITION
    assert [r["image_id"] for r in first] == sorted(
        (r["image_id"] for r in first), key=lambda i: controls.rank(ORDER_SEED, i))
    assert all(r["position"] < 8 if r["stratum"] == "wrong_target" else r["position"] < 6 for r in first)


def test_a_rejected_item_is_replaced_from_its_own_stratum_and_never_re_enters():
    cands = candidates()
    first = controls.replay(cands, [], stored())["next_round"]
    rejected = next(r["image_id"] for r in first if r["stratum"] == "poor_crop")
    reviews = review(1, first, wrong={rejected})
    state = controls.replay(cands, reviews, stored())
    assert len(state["next_round"]) == 1
    replacement = state["next_round"][0]
    assert replacement["stratum"] == "poor_crop" and replacement["position"] == 6
    assert replacement["replaces"] == rejected and replacement["image_id"] != rejected
    done = controls.replay(cands, reviews + review(2, state["next_round"]), stored())
    assert done["complete"] and rejected not in done["confirmed"]["poor_crop"]
    assert {k: len(v) for k, v in done["confirmed"].items()} == controls.COMPOSITION


def test_an_exhausted_stratum_stops_the_build():
    cands = candidates()
    cands["strata"]["poor_crop"] = cands["strata"]["poor_crop"][:6]
    first = controls.replay(cands, [], stored())["next_round"]
    rejected = next(r["image_id"] for r in first if r["stratum"] == "poor_crop")
    state = controls.replay(cands, review(1, first, wrong={rejected}), stored())
    assert state["stopped"] == "poor_crop candidates exhausted" and not state["next_round"]


def test_a_rejected_wrong_target_frame_stops_the_build():
    first = controls.replay(candidates(), [], stored())["next_round"]
    rejected = next(r["image_id"] for r in first if r["stratum"] == "wrong_target")
    state = controls.replay(candidates(), review(1, first, wrong={rejected}), stored())
    assert state["stopped"] == "a wrong_target control was rejected" and not state["complete"]


@pytest.mark.parametrize("change,message", [
    (lambda rows: rows.reverse(), "review order"),
    (lambda rows: rows[0].update(stored="usable" if rows[0]["stored"] != "usable" else "poor_crop"), "stored label"),
    (lambda rows: rows[0].update(decision="rejected"), "decision"),
    (lambda rows: rows[0].update(blind="maybe"), "blind label"),
])
def test_replay_rejects_records_that_break_the_rules(change, message):
    first = controls.replay(candidates(), [], stored())["next_round"]
    rows = review(1, first)
    change(rows)
    with pytest.raises(ValueError, match=message):
        controls.replay(candidates(), rows, stored())


def test_round_sheet_hides_stratum_position_and_labels(tmp_path):
    first = controls.replay(candidates(), [], stored())["next_round"]
    source = tmp_path / "source"
    for kind in ("full", "crop"):
        (source / kind).mkdir(parents=True)
        for item in first:
            Image.new("RGB", (8, 8), (1, 2, 3)).save(source / kind / f"{item['image_id']}.jpg")
    sheet = controls.write_round_sheet(first, 1, source, tmp_path / "round1")
    public = json.loads((tmp_path / "round1" / "sheet.json").read_text())
    assert [i["token"] for i in public["items"]] == [f"r1-{n:02}" for n in range(1, 21)]
    text = json.dumps(public)
    for hidden in ("stratum", "position", "image_id", "wrong_target", "poor_crop"):
        assert hidden not in text
    assert {i["token"]: i["image_id"] for i in sheet} == {f"r1-{n:02}": r["image_id"] for n, r in enumerate(first, 1)}
    assert not Image.open(tmp_path / "round1" / "r1-01_crop.jpg").getexif()


def test_record_writes_blind_labels_before_the_reveal_and_refuses_changes(tmp_path):
    first = controls.replay(candidates(), [], stored())["next_round"]
    sheet = [{**item, "token": f"r1-{n:02}"} for n, item in enumerate(first, 1)]
    blind = {i["token"]: stored()[str(i["image_id"])] for i in sheet}
    path = tmp_path / "validation.json"
    controls.record_round(path, candidates(), stored(), sheet, blind, notes={})
    data = json.loads(path.read_text())
    assert len(data["reviews"]) == 20 and all(r["decision"] == "confirmed" for r in data["reviews"])
    with pytest.raises(ValueError, match="already recorded"):
        controls.record_round(path, candidates(), stored(), sheet, blind, notes={})
    with pytest.raises(ValueError, match="every item"):
        controls.record_round(tmp_path / "other.json", candidates(), stored(), sheet,
                              dict(list(blind.items())[:5]), notes={})


def test_lock_writes_a_d01_to_d20_draw_and_hashes_every_artifact(tmp_path):
    cands = candidates()
    first = controls.replay(cands, [], stored())["next_round"]
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({"reviews": review(1, first)}))
    source = tmp_path / "source"
    for kind in ("full", "crop"):
        (source / kind).mkdir(parents=True)
        for item in first:
            Image.new("RGB", (8, 8), (4, 5, 6)).save(source / kind / f"{item['image_id']}.jpg")
    rubric = tmp_path / "rubric.txt"
    rubric.write_text("Grade the red box.\n")
    out = controls.lock(tmp_path, cands, stored(), validation, source, rubric, repo=tmp_path)
    key = json.loads(out["answer_key"].read_text())
    manifest = json.loads(out["manifest"].read_text())
    receipt = json.loads(out["lock"].read_text())
    assert sorted(key) == [f"d{n:02}" for n in range(1, 21)]
    assert Counter_of(key) == {"wrong_target": 8, "poor_crop": 6, "usable": 6}
    assert [i["id"] for i in manifest["items"]] == sorted(key)
    for name in ("manifest", "answer_key", "validation", "rubric"):
        assert receipt["files"][name]["sha256"] == controls.sha256(tmp_path / receipt["files"][name]["path"])
    assert receipt["locked_at"]
    with pytest.raises(FileExistsError):
        controls.lock(tmp_path, cands, stored(), validation, source, rubric, repo=tmp_path)


def test_lock_refuses_an_incomplete_review(tmp_path):
    cands = candidates()
    first = controls.replay(cands, [], stored())["next_round"]
    rejected = next(r["image_id"] for r in first if r["stratum"] == "usable")
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({"reviews": review(1, first, wrong={rejected})}))
    with pytest.raises(ValueError, match="not complete"):
        controls.lock(tmp_path, cands, stored(), validation, tmp_path, tmp_path / "rubric.txt", repo=tmp_path)


def Counter_of(key):
    from collections import Counter
    return dict(Counter(v["grade"] for v in key.values()))


# --- Revision 3 (2026-11-09): round 2 mixes a wrong_target spare batch with the poor_crop replacement ---

BATCH_IDS = list(range(500, 524))


def round1_stop():
    """Round 1 with 2 wrong_target and 1 poor_crop rejected, as in the real record."""
    cands = candidates()
    first = controls.replay(cands, [], stored())["next_round"]
    wrong = [r["image_id"] for r in first if r["stratum"] == "wrong_target"][:2]
    wrong.append(next(r["image_id"] for r in first if r["stratum"] == "poor_crop"))
    return cands, review(1, first, wrong=set(wrong))


def batch_for(cands):
    low, rest = BATCH_IDS[:16], BATCH_IDS[16:]
    replacement = cands["strata"]["poor_crop"][6]
    return {"spare_seed": "test-spares", "review_order_seed": "test-order-4",
            "batch_low": low, "batch_rest": rest, "poor_crop_replacement": {"image_id": replacement, "position": 6},
            "round2_review_order": sorted(BATCH_IDS + [replacement], key=lambda i: controls.rank("test-order-4", i))}


def round2(cands, batch, round1, labels_by_id, round_number=2):
    expected = controls.replay_rev3(cands, batch, round1, [], stored())["next_round"]
    rows = []
    for item in expected:
        known = stored().get(str(item["image_id"]))
        label = labels_by_id.get(item["image_id"], known or "usable")  # replacements default to confirmed
        rows.append({**item, "round": round_number, "blind": label, "stored": known,
                     "decision": "labelled" if known is None else controls.decide(label, known)})
    return rows


def spare_order(batch):
    return sorted(batch["batch_low"] + batch["batch_rest"], key=lambda i: controls.rank(batch["spare_seed"], i))


def test_rev3_round2_is_the_frozen_batch_plus_the_replacement_in_frozen_order():
    cands, round1 = round1_stop()
    batch = batch_for(cands)
    nxt = controls.replay_rev3(cands, batch, round1, [], stored())["next_round"]
    assert [r["image_id"] for r in nxt] == batch["round2_review_order"]
    replacement = [r for r in nxt if r["kind"] == "replacement"]
    assert len(replacement) == 1 and replacement[0]["position"] == 6 and replacement[0]["stratum"] == "poor_crop"
    assert replacement[0]["replaces"] == next(r["image_id"] for r in round1
                                             if r["stratum"] == "poor_crop" and r["decision"] == "rejected")
    assert {r["kind"] for r in nxt} == {"batch", "replacement"}


def test_rev3_needs_round1_to_have_stopped_on_wrong_target():
    cands = candidates()
    first = controls.replay(cands, [], stored())["next_round"]
    with pytest.raises(ValueError, match="round 1"):
        controls.replay_rev3(cands, batch_for(cands), review(1, first), [], stored())


def test_rev3_takes_the_first_two_wrong_target_labels_in_spare_order():
    cands, round1 = round1_stop()
    batch = batch_for(cands)
    order = spare_order(batch)
    picks = {order[3]: "wrong_target", order[9]: "wrong_target", order[20]: "wrong_target"}
    state = controls.replay_rev3(cands, batch, round1, round2(cands, batch, round1, picks), stored())
    assert state["complete"]
    assert state["new_wrong_target"] == [order[3], order[9]]
    assert {k: len(v) for k, v in state["confirmed"].items()} == controls.COMPOSITION
    assert order[20] not in state["confirmed"]["wrong_target"]


def test_rev3_fewer_than_two_wrong_target_labels_stops():
    cands, round1 = round1_stop()
    batch = batch_for(cands)
    state = controls.replay_rev3(cands, batch, round1,
                                 round2(cands, batch, round1, {spare_order(batch)[0]: "wrong_target"}), stored())
    assert state["stopped"] == "fewer than 2 wrong_target labels in the batch" and not state["complete"]


def test_rev3_rejected_replacement_goes_to_a_single_item_round_3():
    cands, round1 = round1_stop()
    batch = batch_for(cands)
    order = spare_order(batch)
    replacement = batch["poor_crop_replacement"]["image_id"]
    rows = round2(cands, batch, round1, {order[0]: "wrong_target", order[1]: "wrong_target", replacement: "unsure"})
    state = controls.replay_rev3(cands, batch, round1, rows, stored())
    assert not state["complete"] and len(state["next_round"]) == 1
    third = state["next_round"][0]
    assert third["position"] == 7 and third["replaces"] == replacement and third["kind"] == "replacement"
    done = controls.replay_rev3(cands, batch, round1, rows + review(3, state["next_round"]), stored())
    assert done["complete"]


def test_rev3_batch_rows_carry_no_stored_label():
    cands, round1 = round1_stop()
    batch = batch_for(cands)
    rows = round2(cands, batch, round1, {})
    row = next(r for r in rows if r["kind"] == "batch")
    row["stored"] = "usable"
    with pytest.raises(ValueError, match="batch"):
        controls.replay_rev3(cands, batch, round1, rows, stored())


def test_rendered_sheet_uses_the_renderer_and_hides_kind(tmp_path):
    cands, round1 = round1_stop()
    nxt = controls.replay_rev3(cands, batch_for(cands), round1, [], stored())["next_round"]
    calls = []

    def render(item, full, crop):
        calls.append(item["image_id"])
        for target in (full, crop):
            Image.new("RGB", (8, 8), (9, 9, 9)).save(target)

    sheet = controls.write_round_sheet(nxt, 2, None, tmp_path / "round2", render=render)
    assert calls == [r["image_id"] for r in nxt]
    text = (tmp_path / "round2" / "sheet.json").read_text()
    for hidden in ("batch", "replacement", "stratum", "position", "image_id"):
        assert hidden not in text
    assert [s["token"] for s in sheet] == [f"r2-{n:02}" for n in range(1, len(nxt) + 1)]


def test_rev3_lock_renders_all_20_controls_and_hashes_both_records(tmp_path):
    cands, round1 = round1_stop()
    batch = batch_for(cands)
    order = spare_order(batch)
    rows = round2(cands, batch, round1, {order[0]: "wrong_target", order[1]: "wrong_target"})
    first_record, second_record = tmp_path / "round1.json", tmp_path / "round2.json"
    first_record.write_text(json.dumps({"reviews": round1}))
    second_record.write_text(json.dumps({"reviews": rows}))
    rubric = tmp_path / "rubric.txt"
    rubric.write_text("Grade the red box.\n")
    rendered = []

    def render(item, full, crop):
        rendered.append(item["image_id"])
        for target in (full, crop):
            Image.new("RGB", (8, 8), (1, 1, 1)).save(target)

    out = controls.lock_rev3(tmp_path, cands, batch, stored(), first_record, second_record, rubric, render,
                             repo=tmp_path)
    key = json.loads(out["answer_key"].read_text())
    receipt = json.loads(out["lock"].read_text())
    assert sorted(key) == [f"d{n:02}" for n in range(1, 21)] and len(rendered) == 20
    assert Counter_of(key) == controls.COMPOSITION
    assert {v["image_id"] for v in key.values() if v["grade"] == "wrong_target"} >= {order[0], order[1]}
    for name in ("manifest", "answer_key", "round1", "round2", "rubric"):
        assert receipt["files"][name]["sha256"] == controls.sha256(tmp_path / receipt["files"][name]["path"])
