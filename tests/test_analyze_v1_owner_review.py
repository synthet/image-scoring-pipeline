"""The owner review replay must validate the frozen cohort and box identity."""

import json

import pytest

from scripts.research.detector_benchmark.analyze_v1_owner_review import analyze


def _review(tmp_path):
    box_root = tmp_path / "box_page"
    box_root.mkdir()
    (tmp_path / "cohort.csv").write_text(
        "image_id,file_path,stratum\n1,private-a,det_high_small\n"
        "2,private-b,det_high_small\n3,private-c,no_detection\n", encoding="utf-8"
    )
    (tmp_path / "labels.csv").write_text(
        "image_id,label\n1,bird\n2,no_bird\n3,bird\n", encoding="utf-8"
    )
    (tmp_path / "sampling.json").write_text(json.dumps({
        "sample": {"det_high_small": 2, "no_detection": 1},
        "population": [{"stratum": "det_high_small", "images": 20}],
    }), encoding="utf-8")
    (box_root / "manifest.json").write_text(json.dumps({
        "rows": [{"image_id": 1, "run_id": 10, "region_id": 20}],
    }), encoding="utf-8")
    (box_root / "box_labels.csv").write_text(
        "image_id,run_id,region_id,box_label\n1,10,20,usable\n", encoding="utf-8"
    )
    return tmp_path


def test_review_replay_reports_aggregate_outcomes(tmp_path):
    result = analyze(_review(tmp_path))
    assert result["reviewed_images"] == 3
    assert result["detected_primary_outcomes"] == {"usable": 1, "presence_no_bird": 1}
    assert result["no_detection_presence"] == {"bird": 1}
    assert result["detected_strata"]["det_high_small"]["population"] == 20
    assert "private-a" not in json.dumps(result)


def test_review_replay_rejects_changed_primary_region(tmp_path):
    root = _review(tmp_path)
    (root / "box_page" / "box_labels.csv").write_text(
        "image_id,run_id,region_id,box_label\n1,10,21,usable\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="changed run or region"):
        analyze(root)
