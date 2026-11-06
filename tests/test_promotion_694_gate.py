"""Frozen gate guards; synthetic votes never replace the private owner labels."""
import json

import pytest

from scripts.research.detector_benchmark import promotion_694_gate as gate


def vote(grade="usable", presence="bird"):
    return {"presence": presence, "grade": grade, "reason": "Visible evidence"}


def test_parse_accepts_original_and_wrapper_envelopes():
    for envelope in ("items", "images"):
        raw = json.dumps({envelope: [{"id": "p01", **vote()}]})
        assert gate.parse_reply("```json\n" + raw + "\n```", {"p01"}) == {"p01": vote()}


@pytest.mark.parametrize("rows", [
    [], [{"id": "other", **vote()}],
    [{"id": "p01", **vote()}, {"id": "p01", **vote()}],
    [{"id": "p01", **vote(grade="excellent")}],
    [{"id": "p01", **vote(), "reason": None}], [None],
])
def test_parse_rejects_missing_duplicate_and_invalid_rows(rows):
    with pytest.raises(ValueError):
        gate.parse_reply(json.dumps({"images": rows}), {"p01"})


def test_conflicting_envelopes_are_rejected():
    with pytest.raises(ValueError):
        gate.parse_reply(json.dumps({"images": [{"id": "p01", **vote()}], "items": []}), {"p01"})


@pytest.mark.parametrize("correct,parsed,qualified", [(18, 20, True), (17, 20, False),
                                                    (18, 19, True), (18, 18, False)])
def test_calibration_thresholds(correct, parsed, qualified):
    answers = {f"p{i:02}": {"usable": i < 6} for i in range(20)}
    votes = {}
    for i, (token, owner) in enumerate(answers.items()):
        if i >= parsed:
            continue
        usable = owner["usable"] if i < correct else not owner["usable"]
        votes[token] = vote("usable" if usable else "poor_crop")
    result = gate.calibration_stats(votes, answers)
    assert result["correct"] == correct
    assert result["qualified"] is qualified


def test_consensus_needs_three_judges_and_does_not_merge_negative_categories():
    with pytest.raises(ValueError):
        gate.resolve_votes({"agy": vote(), "cursor": vote()})
    assert gate.resolve_votes({"agy": vote(), "cursor": vote(), "gemini": vote("poor_crop")}) == "usable"
    split = {"agy": vote("poor_crop"), "cursor": vote("wrong_target"),
             "gemini": vote("unsure", "unsure")}
    assert gate.resolve_votes(split) is None
    assert gate.resolve_votes(split, {"label": "poor_crop", "confidence": 0.7}) == "poor_crop"


@pytest.mark.parametrize("confidence", [0.69, float("nan"), float("inf"), True])
def test_unreliable_adjudication_stays_unresolved(confidence):
    split = {"agy": vote(), "cursor": vote("poor_crop"), "gemini": vote("wrong_target")}
    assert gate.resolve_votes(split, {"label": "usable", "confidence": confidence}) is None


def sample():
    return [{"id": f"v{band}{i}", "image_id": b * 1000 + i, "band": band,
             "folder_id": i // 10} for b, band in enumerate(("large", "medium", "small"))
            for i in range(130)]


def test_gate_reports_primary_conservative_and_folder_sensitivity():
    frames = sample()
    labels = {r["id"]: "usable" for r in frames}
    for row in frames:
        if row["band"] == "medium" and row["image_id"] % 1000 < 30:
            labels[row["id"]] = None
    result = gate.analyze_bands(frames, labels)
    assert result["large"]["passed"]
    assert result["medium"]["passed"]
    assert result["medium"]["unresolved"] == 30
    assert result["medium"]["conservative_wilson"][0] < 0.9
    assert result["small"]["use"] == "geometry_only"
    assert result["large"]["one_per_folder"]["total"] == 13


def test_missing_or_extra_labels_and_wrong_sample_sizes_fail():
    frames = sample()
    labels = {r["id"]: "usable" for r in frames}
    with pytest.raises(ValueError):
        gate.analyze_bands(frames[:-1], labels)
    labels.pop(frames[0]["id"])
    with pytest.raises(ValueError):
        gate.analyze_bands(frames, labels)


def test_artifact_drift_and_path_escape_are_rejected(tmp_path):
    path = tmp_path / "input.json"
    path.write_text("original")
    files = {"input.json": gate.sha256(path)}
    gate.verify_hashes(tmp_path, files)
    path.write_text("changed")
    with pytest.raises(ValueError):
        gate.verify_hashes(tmp_path, files)
    with pytest.raises(ValueError):
        gate.verify_hashes(tmp_path, {"../outside.json": "0" * 64})


def panel_fixture(tmp_path):
    image = tmp_path / "blind.jpg"
    image.write_bytes(b"image fixture")
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({"images": [{"id": "p01", **vote()}]}))
    items = [{"id": "p01", "files": ["blind.jpg"]}]
    panel = {"stages": {"build": {"items": items}, "run": {"judges": [
        {"agent": "cursor", "ok": True, "outputFile": "raw.json"}]}}}
    path = tmp_path / "panel.json"
    path.write_text(json.dumps(panel))
    return path, panel, items


def test_collect_checks_image_identity_and_retains_raw_hash(tmp_path):
    path, panel, items = panel_fixture(tmp_path)
    votes, proof, failures = gate.collect_panels(tmp_path, [path], items, ("cursor",))
    assert votes["cursor"]["p01"] == vote()
    assert proof[0]["sha256"] == gate.sha256(tmp_path / "raw.json")
    assert not failures
    panel["stages"]["build"]["items"] = [{"id": "p01", "files": ["different.jpg"]}]
    path.write_text(json.dumps(panel))
    with pytest.raises(ValueError, match="image manifest mismatch"):
        gate.collect_panels(tmp_path, [path], items, ("cursor",))


def test_collect_rejects_reused_panel_and_duplicate_accepted_votes(tmp_path):
    path, panel, items = panel_fixture(tmp_path)
    with pytest.raises(ValueError, match="reused panel"):
        gate.collect_panels(tmp_path, [path, path], items, ("cursor",))
    other_raw = tmp_path / "other.json"
    other_raw.write_bytes((tmp_path / "raw.json").read_bytes())
    panel["stages"]["run"]["judges"][0]["outputFile"] = "other.json"
    other = tmp_path / "panel2.json"
    other.write_text(json.dumps(panel))
    with pytest.raises(ValueError, match="duplicate accepted"):
        gate.collect_panels(tmp_path, [path, other], items, ("cursor",))


def test_collect_rejects_reused_raw_receipts_and_unknown_judges(tmp_path):
    path, panel, items = panel_fixture(tmp_path)
    other = tmp_path / "panel2.json"
    other.write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match="reused raw"):
        gate.collect_panels(tmp_path, [path, other], items, ("cursor",))
    panel["stages"]["run"]["judges"][0]["agent"] = "grok"
    path.write_text(json.dumps(panel))
    with pytest.raises(ValueError, match="unexpected judge"):
        gate.collect_panels(tmp_path, [path], items, ("cursor",))


def test_failed_or_malformed_batch_never_produces_votes(tmp_path):
    path, panel, items = panel_fixture(tmp_path)
    for ok, raw in ((False, "ignored"), (True, "not json")):
        panel["stages"]["run"]["judges"][0]["ok"] = ok
        path.write_text(json.dumps(panel))
        (tmp_path / "raw.json").write_text(raw)
        votes, _, failures = gate.collect_panels(tmp_path, [path], items, ("cursor",))
        assert votes == {"cursor": {}}
        assert len(failures) == 1


def test_all_unresolved_band_cannot_pass():
    frames = sample()
    result = gate.analyze_bands(frames, {r["id"]: None for r in frames})
    assert not any(r["passed"] for r in result.values())


def test_blind_evidence_rejects_exif_original_names_and_changed_pixels(tmp_path):
    from PIL import Image

    files = ["v001_overview.jpg", "v001_crop.jpg"]
    item = {"id": "v001", "files": files}
    for name in files:
        Image.new("RGB", (8, 8)).save(tmp_path / name)
    hashes = {name: gate.sha256(tmp_path / name) for name in files}
    gate.verify_blind_files(tmp_path, item, hashes)
    with pytest.raises(ValueError, match="filenames"):
        gate.verify_blind_files(tmp_path, {"id": "v001", "files": ["original.nef"]}, hashes)
    exif = Image.Exif()
    exif[270] = "private metadata fixture"
    Image.new("RGB", (8, 8)).save(tmp_path / files[0], exif=exif)
    with pytest.raises(ValueError, match="hash changed"):
        gate.verify_blind_files(tmp_path, item, hashes)
    hashes[files[0]] = gate.sha256(tmp_path / files[0])
    with pytest.raises(ValueError, match="private metadata"):
        gate.verify_blind_files(tmp_path, item, hashes)


def control_answers():
    return {f"c{n:02}": {"usable": True} for n in range(1, 21)}


def control_votes(correct, parsed=20):
    tokens = list(control_answers())[:parsed]
    return {t: vote("usable" if n < correct else "poor_crop") for n, t in enumerate(tokens)}


def chain_fixture(tmp_path, agent="cursor", **judge):
    path, panel, items = panel_fixture(tmp_path)
    panel["stages"]["run"]["judges"][0].update(agent=agent, **judge)
    path.write_text(json.dumps(panel))
    return path, items


def test_seats_are_the_frozen_four_tools():
    assert set(gate.SEATS) == {"claude", "codex", "cursor", "antigravity"}
    assert "gemini" not in gate.JUDGES
    assert all(len(chain) == 3 for chain in gate.SEATS.values())


def test_chain_groups_votes_by_model_and_records_it(tmp_path):
    path, items = chain_fixture(tmp_path, model="grok-4.7", reportedModel="grok-4.7[fast=true]")
    votes, proof, _ = gate.collect_panels(tmp_path, [path], items, ("cursor",), chains=gate.SEATS)
    assert votes["cursor"]["grok-4.7"]["p01"] == vote()
    assert proof[0]["model"] == "grok-4.7"


@pytest.mark.parametrize("judge,message", [
    ({}, "outside its chain"),
    ({"model": "gpt-6.1-sol"}, "outside its chain"),
    ({"model": "grok-4.7"}, "different model"),
    ({"model": "grok-4.7", "reportedModel": "composer-2.5[fast=true]"}, "different model"),
])
def test_chain_rejects_unproven_models(tmp_path, judge, message):
    path, items = chain_fixture(tmp_path, **judge)
    with pytest.raises(ValueError, match=message):
        gate.collect_panels(tmp_path, [path], items, ("cursor",), chains=gate.SEATS)


def test_technical_failure_reaches_the_next_model():
    stats, allowed = gate.qualify_seat({"a": {}, "b": control_votes(20)}, control_answers(), ("a", "b", "c"))
    assert allowed == ["b"]
    assert stats["a"]["parsed"] == 0


def test_too_few_parsed_replies_is_technical():
    _, allowed = gate.qualify_seat({"a": control_votes(18, parsed=18), "b": control_votes(19)},
                                   control_answers(), ("a", "b"))
    assert allowed == ["b"]


def test_bar_failure_ends_the_seat():
    _, allowed = gate.qualify_seat({"a": control_votes(17)}, control_answers(), ("a", "b"))
    assert allowed == []


def test_fallback_after_a_bar_failure_is_rejected():
    with pytest.raises(ValueError, match="after a bar failure"):
        gate.qualify_seat({"a": control_votes(17), "b": control_votes(20)}, control_answers(), ("a", "b"))


def test_a_takeover_model_must_pass_the_same_draw():
    _, allowed = gate.qualify_seat({"a": control_votes(20), "b": control_votes(18)}, control_answers(), ("a", "b"))
    assert allowed == ["a", "b"]
    _, allowed = gate.qualify_seat({"a": control_votes(20), "b": control_votes(17)}, control_answers(), ("a", "b"))
    assert allowed == ["a"]


def test_seat_votes_keep_only_qualified_models():
    assert gate.seat_votes({"a": {"v001": vote()}, "b": {"v002": vote()}, "c": {}}, ["a", "b"]).keys() == {"v001", "v002"}
    with pytest.raises(ValueError, match="did not qualify"):
        gate.seat_votes({"a": {"v001": vote()}}, ["b"])
    with pytest.raises(ValueError, match="duplicate accepted"):
        gate.seat_votes({"a": {"v001": vote()}, "b": {"v001": vote()}}, ["a", "b"])


def test_consensus_follows_the_number_of_qualified_seats():
    three = {"claude": vote(), "codex": vote(), "cursor": vote("poor_crop")}
    assert gate.resolve_votes(three) == "usable"
    four = {**three, "antigravity": vote("poor_crop")}
    assert gate.resolve_votes(four) is None
    assert gate.resolve_votes({**four, "cursor": vote()}) == "usable"
