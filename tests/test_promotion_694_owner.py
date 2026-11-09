"""#694 owner-labelled validation (2026-11-09): order, final-on-record batches and the gate's analysis."""
import hashlib
import json

import pytest

from scripts.research.detector_benchmark import promotion_694_gate as gate
from scripts.research.detector_benchmark import promotion_694_owner as owner


def sample():
    return [{"image_id": b * 1000 + i, "band": band, "folder_id": i // 10}
            for b, band in enumerate(("large", "medium", "small")) for i in range(130)]


def items():
    return owner.mixed_order([r["image_id"] for r in sample()])


def batch_labels(order, batch, label="usable"):
    return {r["token"]: label for r in order if r["batch"] == batch}


def record_all(path, order, label_for=lambda row: "usable"):
    for batch in range(1, 14):
        rows = [r for r in order if r["batch"] == batch]
        owner.record_batch(path, order, batch, {r["token"]: label_for(r) for r in rows}, {})


def test_order_follows_the_frozen_rule_in_13_batches_of_30():
    ids = [r["image_id"] for r in sample()]
    order = owner.mixed_order(ids)
    assert order == owner.mixed_order(list(reversed(ids)))
    expected = sorted(ids, key=lambda i: hashlib.sha256(f"{owner.SEED}:{i}".encode()).hexdigest())
    assert [r["image_id"] for r in order] == expected
    assert [r["token"] for r in order[:2]] == ["v001", "v002"] and order[-1]["token"] == "v390"
    assert [sum(r["batch"] == b for r in order) for b in range(1, 14)] == [30] * 13


def test_a_batch_cannot_be_recorded_twice_or_out_of_order(tmp_path):
    order, path = items(), tmp_path / "record.json"
    with pytest.raises(ValueError, match="in order"):
        owner.record_batch(path, order, 2, batch_labels(order, 2), {})
    owner.record_batch(path, order, 1, batch_labels(order, 1), {})
    with pytest.raises(ValueError, match="already recorded"):
        owner.record_batch(path, order, 1, batch_labels(order, 1, "poor_crop"), {})
    assert {r["label"] for r in json.loads(path.read_text())["batches"][0]["rows"]} == {"usable"}


@pytest.mark.parametrize("change", ["missing", "extra", "invalid", "stray_note"])
def test_a_batch_must_label_exactly_its_frames(tmp_path, change):
    order = items()
    labels, notes = batch_labels(order, 1), {}
    if change == "missing":
        labels.pop(next(iter(labels)))
    elif change == "extra":
        labels["v031"] = "usable"
    elif change == "invalid":
        labels[next(iter(labels))] = "excellent"
    else:
        notes["v031"] = "not in this batch"
    with pytest.raises(ValueError):
        owner.record_batch(tmp_path / "record.json", order, 1, labels, notes)


def test_recording_reports_no_label_counts(tmp_path):
    order = items()
    shown = owner.record_batch(tmp_path / "record.json", order, 1, batch_labels(order, 1, "poor_crop"),
                               {"v001": "head clipped"}, original_sha256="ab" * 32)
    assert shown == {"batch": 1, "recorded": 30, "batches_done": 1, "batches_left": 12}
    row = json.loads((tmp_path / "record.json").read_text())["batches"][0]
    assert row["original_sha256"] == "ab" * 32 and set(row["rows"][0]) == {"token", "label", "note", "batch",
                                                                          "recorded_at"}


def test_note_conflicts_flag_a_note_that_names_another_outcome():
    flagged = owner.note_conflicts({"v001": "usable", "v002": "poor_crop", "v003": "usable"},
                                   {"v001": "not a bird", "v002": "head clipped", "v003": ""})
    assert flagged == ["v001"]


def test_analysis_needs_every_batch(tmp_path):
    order, path = items(), tmp_path / "record.json"
    owner.record_batch(path, order, 1, batch_labels(order, 1), {})
    with pytest.raises(ValueError, match="all 390"):
        gate.owner_bands(sample(), order, json.loads(path.read_text()))


def test_analysis_matches_analyze_bands_with_unsure_unresolved(tmp_path):
    order, path = items(), tmp_path / "record.json"
    by_id = {r["image_id"]: r for r in sample()}

    def label_for(row):
        source = by_id[row["image_id"]]
        if source["band"] == "medium" and source["image_id"] % 1000 < 20:
            return "unsure"
        return "poor_crop" if source["band"] == "small" and source["image_id"] % 1000 < 10 else "usable"

    record_all(path, order, label_for)
    result = gate.owner_bands(sample(), order, json.loads(path.read_text()))
    token = {r["image_id"]: r["token"] for r in order}
    frames = [{"id": token[r["image_id"]], "band": r["band"], "folder_id": r["folder_id"]} for r in sample()]
    labels = {r["token"]: (None if label_for(r) == "unsure" else label_for(r)) for r in order}
    assert result == gate.analyze_bands(frames, labels)
    assert result["medium"]["unresolved"] == 20 and result["small"]["usable"] == 120


def test_analysis_rejects_a_record_edited_out_of_order(tmp_path):
    order, path = items(), tmp_path / "record.json"
    record_all(path, order)
    record = json.loads(path.read_text())
    record["batches"][0]["rows"][0]["token"] = "v031"
    with pytest.raises(ValueError):
        gate.owner_bands(sample(), order, record)


def test_frozen_order_and_receipt_are_checked(tmp_path, monkeypatch):
    rows = sample()
    (tmp_path / "pre.md").write_text("frozen\n", encoding="utf-8")
    (tmp_path / owner.ORDER).write_text(json.dumps({"seed": owner.SEED, "batch_size": 30,
                                                    "items": owner.mixed_order([r["image_id"] for r in rows])}),
                                        encoding="utf-8")
    receipt = {"preregistration": "pre.md", "preregistration_sha256": gate.sha256(tmp_path / "pre.md"),
               "order": owner.ORDER, "order_sha256": gate.sha256(tmp_path / owner.ORDER)}
    (tmp_path / owner.FREEZE).write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setattr(owner, "FREEZE_SHA256", gate.sha256(tmp_path / owner.FREEZE))
    assert len(owner.load_frozen(tmp_path, rows)) == 390
    with pytest.raises(ValueError, match="sample"):
        owner.load_frozen(tmp_path, rows[:-1] + [{**rows[-1], "image_id": 99999}])
    (tmp_path / "pre.md").write_text("edited\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        owner.load_frozen(tmp_path, rows)
