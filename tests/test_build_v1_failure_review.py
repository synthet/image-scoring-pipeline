"""The failure page uses exactly the frozen owner-review cases and candidate rules."""

import csv
from pathlib import Path

import pytest

from scripts.research.detector_benchmark.build_v1_failure_review import (
    _cascade_candidates,
    load_cases,
    prepare,
)


def _write_csv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _frozen_review(root: Path):
    cohort = []
    presence = []
    boxes = []
    for iid in range(1, 217):
        detected = iid <= 144
        cohort.append({"image_id": iid, "stratum": "det_high_small" if detected else "no_detection"})
        if iid <= 79:
            label = "no_bird"
        elif detected:
            label = "bird"
        else:
            label = "no_bird"
        presence.append({"image_id": iid, "label": label})
        if 80 <= iid <= 144:
            grade = "poor_crop" if iid <= 106 else "wrong_target" if iid <= 114 else "usable"
            boxes.append({"image_id": iid, "run_id": iid + 1000,
                          "region_id": iid + 2000, "box_label": grade})
    _write_csv(root / "cohort.csv", ("image_id", "stratum"), cohort)
    _write_csv(root / "labels.csv", ("image_id", "label"), presence)
    _write_csv(root / "box_page" / "box_labels.csv",
               ("image_id", "run_id", "region_id", "box_label"), boxes)


def test_prepare_freezes_79_false_and_35_bad_primary_cases(tmp_path):
    _frozen_review(tmp_path)
    cases = load_cases(tmp_path)
    assert len(cases) == 114
    assert {case["kind"] for case in cases} == {"false_detection", "bad_primary"}
    out = tmp_path / "failure_review" / "inference_input"
    prepare(tmp_path, out)
    with (out / "cohort.csv").open(newline="", encoding="utf-8") as handle:
        ids = {int(row["image_id"]) for row in csv.DictReader(handle)}
    assert ids == set(range(1, 115))


def test_prepare_rejects_changed_primary_review(tmp_path):
    _frozen_review(tmp_path)
    path = tmp_path / "box_page" / "box_labels.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("80,1080,2080,poor_crop",
                                                        "80,1080,2080,usable"), encoding="utf-8")
    with pytest.raises(ValueError, match="case counts changed"):
        load_cases(tmp_path)


def test_cascade_candidates_keep_threshold_notes_and_valid_refine():
    record = {
        "coco": [
            {"region": [0.1, 0.1, 0.3, 0.3], "conf": 0.42},
            {"region": [0.5, 0.5, 0.6, 0.6], "conf": 0.30},
            {"region": [0.7, 0.7, 0.8, 0.8], "conf": 0.20},
        ],
        "refine": [{"coco_region": [0.5, 0.5, 0.6, 0.6],
                    "yolo": [{"region": [0.51, 0.51, 0.61, 0.61], "conf": 0.8}]}],
    }
    candidates = _cascade_candidates(record)
    assert [c["id"] for c in candidates] == ["coco:0", "coco:1", "refine:0"]
    assert candidates[0]["note"] == "candidate confidence ≥0.40"
    assert candidates[1]["note"] == "below 0.40 candidate threshold"


def test_refine_box_outside_frame_is_clipped_for_display():
    record = {"coco": [{"region": [0.0, 0.0, 0.1, 0.1], "conf": 0.5}],
              "refine": [{"coco_region": [0.0, 0.0, 0.1, 0.1],
                          "yolo": [{"region": [-0.02, -0.02, 0.08, 0.08], "conf": 0.7}]}]}
    candidates = _cascade_candidates(record)
    assert candidates[1]["box"] == [0.0, 0.0, 0.08, 0.08]
    assert "clipped to frame" in candidates[1]["note"]
