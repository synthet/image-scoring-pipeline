import csv
import json

import pytest

from scripts.research.detector_benchmark.analyze_v1_failure_review import analyze


def _inputs(tmp_path):
    manifest = {
        "case_count": 2,
        "items": [
            {"image_id": 1, "kind": "false_detection", "primary_grade": "", "candidates": [
                {"id": "v1:0", "provider": "v1 primary", "primary": True, "box": [0.1, 0.1, 0.3, 0.3], "confidence": 0.8},
                {"id": "coco:0", "provider": "RTMDet animal", "primary": False, "box": [0.11, 0.11, 0.31, 0.31], "confidence": 0.42},
            ]},
            {"image_id": 2, "kind": "bad_primary", "primary_grade": "poor_crop", "candidates": [
                {"id": "v1:0", "provider": "v1 primary", "primary": True, "box": [0.1, 0.1, 0.2, 0.2], "confidence": 0.5},
                {"id": "coco:0", "provider": "RTMDet animal", "primary": False, "box": [0.1, 0.1, 0.3, 0.3], "confidence": 0.5},
            ]},
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    csv_path = tmp_path / "review.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["image_id", "kind", "original_primary_grade", "cause",
                                                    "candidate_id", "provider", "candidate_grade", "reviewed"])
        writer.writeheader()
        writer.writerow({"image_id": 1, "kind": "false_detection", "original_primary_grade": "",
                         "cause": "animal", "candidate_id": "", "provider": "", "candidate_grade": "", "reviewed": 1})
        writer.writerow({"image_id": 2, "kind": "bad_primary", "original_primary_grade": "poor_crop",
                         "cause": "", "candidate_id": "coco:0", "provider": "RTMDet animal",
                         "candidate_grade": "usable", "reviewed": 1})
    return manifest_path, csv_path


def test_analyze_counts_completed_review_and_spatial_overlap(tmp_path):
    manifest_path, csv_path = _inputs(tmp_path)
    summary = analyze(manifest_path, csv_path)
    assert summary["case_count"] == 2
    assert summary["false_detection_causes"] == {"animal": 1}
    assert summary["bad_primary_with_usable_alternative"] == 1
    assert summary["false_detection_rtmdet_frame_and_spatial_checks"]["conf_ge_0.40_iou_ge_0.50"] == 1


def test_analyze_rejects_incomplete_case(tmp_path):
    manifest_path, csv_path = _inputs(tmp_path)
    csv_path.write_text(csv_path.read_text(encoding="utf-8").replace("usable,1", "usable,0"), encoding="utf-8")
    with pytest.raises(ValueError, match="not fully reviewed"):
        analyze(manifest_path, csv_path)
