"""Tests for blind compare label scoring."""

import hashlib
import json

import pytest

from scripts.research.detector_benchmark.score_compare_labels import main


def test_score_compare_labels_smoke(tmp_path):
    mapping = {
        "rows": [
            {
                "image_id": 1,
                "stratum": "det_small",
                "option_a_model": "bird_detect_v0.pt",
                "option_b_model": "bird_detect_v1.pt",
                "v0_on_screen": "a",
            },
            {
                "image_id": 2,
                "stratum": "det_small",
                "option_a_model": "bird_detect_v1.pt",
                "option_b_model": "bird_detect_v0.pt",
                "v0_on_screen": "b",
            },
        ]
    }
    map_path = tmp_path / "mapping.json"
    map_path.write_text(json.dumps(mapping), encoding="utf-8")
    labels_path = tmp_path / "labels.csv"
    labels_path.write_text("image_id,pick\n1,a\n2,b\n", encoding="utf-8")
    out = tmp_path / "scores.json"
    assert main(["--labels", str(labels_path), "--mapping", str(map_path), "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["decisive"]["v0_wins"] == 2
    assert payload["decisive"]["v1_wins"] == 0
    assert payload["labels_sha256"] == hashlib.sha256(labels_path.read_bytes()).hexdigest()
    assert payload["mapping_sha256"] == hashlib.sha256(map_path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("label_rows", "message"),
    [
        ("1,a\n", "cover the mapping exactly"),
        ("1,a\n1,b\n2,b\n", "duplicate image IDs"),
        ("1,a\n2,invalid\n", "invalid pick"),
    ],
)
def test_score_compare_labels_rejects_invalid_exports(tmp_path, label_rows, message):
    mapping = {"rows": [
        {"image_id": image_id, "option_a_model": "bird_detect_v0.pt",
         "option_b_model": "bird_detect_v1.pt", "v0_on_screen": "a"}
        for image_id in (1, 2)
    ]}
    map_path = tmp_path / "mapping.json"
    map_path.write_text(json.dumps(mapping), encoding="utf-8")
    labels_path = tmp_path / "labels.csv"
    labels_path.write_text("image_id,pick\n" + label_rows, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        main(["--labels", str(labels_path), "--mapping", str(map_path),
              "--out", str(tmp_path / "scores.json")])
