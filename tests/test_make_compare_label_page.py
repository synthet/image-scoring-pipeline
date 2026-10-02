"""Unit tests for blind v0/v1 compare labeller helpers."""

from scripts.research.detector_benchmark.make_compare_label_page import (
    _box_from_ranked,
    assign_sides,
    boxes_divergent,
)


def test_boxes_divergent_one_missing():
    box = (0.1, 0.1, 0.5, 0.5)
    assert boxes_divergent(None, box) is True
    assert boxes_divergent(box, None) is True
    assert boxes_divergent(None, None) is False


def test_boxes_divergent_high_iou():
    a = (0.1, 0.1, 0.5, 0.5)
    b = (0.11, 0.11, 0.51, 0.51)
    assert boxes_divergent(a, b, iou_threshold=0.85) is False


def test_boxes_divergent_low_iou():
    a = (0.1, 0.1, 0.3, 0.3)
    b = (0.6, 0.6, 0.9, 0.9)
    assert boxes_divergent(a, b, iou_threshold=0.85) is True


def test_box_from_ranked_tuple_region():
    n, conf, x1, y1, x2, y2 = _box_from_ranked(
        {"conf": 0.91, "region": (0.1, 0.2, 0.5, 0.6)}
    )
    assert n == 1
    assert conf == "0.91"
    assert (x1, y1, x2, y2) == ("0.1", "0.2", "0.5", "0.6")


def test_assign_sides_stable():
    assert assign_sides(42) == assign_sides(42)
    assert assign_sides(42) in (True, False)
