"""Comparison logic of the #858 species parity study (no model, no DB)."""
import json

import pytest

from scripts.research import species_parity_858 as SP


def _row(image_id, a_top, b_top, *, a_conf=0.8, b_conf=0.7, a_box=(0.1, 0.1, 0.5, 0.5), b_box=(0.1, 0.1, 0.5, 0.5),
         area=0.16, version="v1", aspect_mismatch=False, min_conf=0.5):
    arm = lambda top, conf, box: {"top1": top, "conf": conf, "box": list(box) if box else None}  # noqa: E731
    return {"image_id": image_id, "area": area, "detector_version": version, "aspect_mismatch": aspect_mismatch,
            "min_confidence": min_conf, "arms": {"a": arm(a_top, a_conf, a_box), "b": arm(b_top, b_conf, b_box)}}


def test_box_iou_identical_disjoint_and_missing():
    assert SP.box_iou([0, 0, 1, 1], [0, 0, 1, 1]) == pytest.approx(1.0)
    assert SP.box_iou([0, 0, 0.2, 0.2], [0.5, 0.5, 0.9, 0.9]) == 0.0
    assert SP.box_iou([0, 0, 0.5, 0.5], [0.25, 0, 0.75, 0.5]) == pytest.approx(1 / 3)
    assert SP.box_iou(None, [0, 0, 1, 1]) is None


def test_wilson_interval_bounds():
    lo, hi = SP.wilson(190, 200)
    assert lo < 0.95 < hi and 0.9 < lo and hi < 0.98
    assert SP.wilson(0, 0) is None
    lo0, hi0 = SP.wilson(0, 10)
    assert lo0 == 0.0 and hi0 > 0.2


def test_normalized_pixel_box_from_embedded_last_bbox():
    assert SP.normalized_pixel_box({"x1": 100, "y1": 50, "x2": 300, "y2": 250, "img_w": 1000, "img_h": 500}) == \
        pytest.approx([0.1, 0.1, 0.3, 0.5])
    assert SP.normalized_pixel_box({"detected": False}) is None
    assert SP.normalized_pixel_box(None) is None


def test_compare_counts_agreement_boxes_and_bands():
    rows = [
        _row(1, "Ardea cinerea", "Ardea cinerea", area=0.01),
        _row(2, "Ardea cinerea", "Ardea alba", area=0.05, b_box=(0.6, 0.6, 0.9, 0.9)),
        _row(3, "Parus major", "Parus major", area=0.2, aspect_mismatch=True),
        _row(4, "Pica pica", "Pica pica", area=0.3, b_box=None),
    ]
    rep = SP.compare(rows)
    assert rep["pairs"] == 4
    assert rep["top1_agree"]["n"] == 3 and rep["top1_agree"]["of"] == 4
    assert rep["box_iou"]["pairs_with_both_boxes"] == 3
    assert rep["box_iou"]["different_box"] == 1          # row 2: disjoint boxes
    assert rep["box_iou"]["b_without_box"] == 1          # row 4: embedded found no bird
    assert rep["aspect_mismatch"] == 1                   # row 3
    assert rep["top1_conf_delta_b_minus_a"]["mean"] == pytest.approx(-0.1)
    assert sum(b["pairs"] for b in rep["by_area_band"].values()) == 4
    assert [d["image_id"] for d in rep["disagreements"]] == [2]


def test_compare_counts_failed_arms_but_does_not_pair_them():
    rows = [_row(1, "A", "A"), _row(2, "A", "A"), _row(3, "A", "A"), _row(4, "A", "B")]
    rows[3]["arms"]["b"] = {"error": "decode failed", "size": None}
    rep = SP.compare(rows)
    assert rep["failed"] == {"a": 0, "b": 1}
    assert rep["pairs"] == 3 and rep["top1_agree"]["n"] == 3


def test_parse_arm():
    assert SP.parse_arm("embedded") == ("embedded", None)
    assert SP.parse_arm("region:box_v1") == ("region", "box_v1")
    with pytest.raises(ValueError):
        SP.parse_arm("region:")
    with pytest.raises(ValueError):
        SP.parse_arm("whole")


def test_draw_is_seeded_and_sorted():
    pool = [{"image_id": i} for i in range(50, 0, -1)]
    a = SP.draw(pool, seed=858, size=10)
    assert a == SP.draw(list(reversed(pool)), seed=858, size=10)
    assert [f["image_id"] for f in a] == sorted(f["image_id"] for f in a)
    with pytest.raises(ValueError):
        SP.draw(pool, seed=1, size=51)


def test_report_writes_json(tmp_path):
    results = tmp_path / "r.jsonl"
    rows = [_row(i, "A", "A", area=0.01 * i) for i in range(1, 5)]
    for r in rows:
        r["arm_specs"] = {"a": "region:box", "b": "embedded"}
    results.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    rep = SP.report(results, tmp_path / "rep.json")
    assert rep["top1_agree"]["rate"] == 1.0
    assert json.loads((tmp_path / "rep.json").read_text())["arm_specs"]["b"] == "embedded"


def test_script_has_no_db_write_statements():
    """AC: the study makes no DB writes; the only SQL it holds is the read-only cohort query."""
    src = (SP._ROOT / "scripts/research/species_parity_858.py").read_text(encoding="utf-8").upper()
    for verb in ("INSERT ", "UPDATE ", "DELETE ", "UPSERT", ".EXECUTE("):
        assert verb not in src


def test_aspect_mismatch_uses_display_aspect():
    assert SP.aspect_mismatch([1024, 683], [8256, 5504]) is False
    assert SP.aspect_mismatch([683, 1024], [8256, 5504]) is True     # rotated rendition
    assert SP.aspect_mismatch(None, [8256, 5504]) is None
    assert SP.aspect_mismatch([1024, 683], [None, None]) is None


def test_stored_output_agreement_counts_abstentions():
    rows = [
        _row(1, "A", "A", a_conf=0.9, b_conf=0.9),
        _row(2, "A", "B", a_conf=0.3, b_conf=0.4),   # top-1 differs, both abstain -> same stored output
        _row(3, "A", "A", a_conf=0.9, b_conf=0.4),   # top-1 same, b abstains -> different stored output
    ]
    rep = SP.compare(rows)
    assert rep["top1_agree"]["n"] == 2
    assert rep["stored_output_agree"]["n"] == 2 and rep["stored_output_agree"]["min_confidence"] == 0.5


def test_compare_splits_by_detector_version():
    rows = [_row(1, "A", "A", version="v0"), _row(2, "A", "B", version="v0"),
            _row(3, "A", "A", version="v1"), _row(4, "A", "A", version="v1")]
    rep = SP.compare(rows)
    assert rep["by_detector_version"]["v0"]["top1_agree"]["n"] == 1
    assert rep["by_detector_version"]["v1"]["top1_agree"]["n"] == 2
    assert "by_detector_version" not in rep["by_detector_version"]["v0"]
