"""Spec 03 (#408): cascade combination as a pure function (AC-7 to AC-14)."""

import pytest

from modules.localization_cascade import (
    DETECTED,
    DISABLED,
    NO_DETECTION,
    RETRYABLE,
    TERMINAL,
    ChildOutcome,
    cascade_config_hash,
    combine,
    iou,
    refine_crop,
)

YOLO_BOX = {"region": (0.4, 0.4, 0.6, 0.6), "conf": 0.8}
COCO_BIG = {"region": (0.1, 0.1, 0.5, 0.5), "conf": 0.7, "cls": "bird"}
COCO_SMALL = {"region": (0.50, 0.50, 0.55, 0.55), "conf": 0.6, "cls": "bird"}  # 0.25% of the frame


def child(status, boxes=(), h="h"):
    return ChildOutcome(status, h, list(boxes))


def test_yolo_detection_wins_and_is_labelled_yolo():
    r = combine(child(DETECTED, [YOLO_BOX], "y"), child(DETECTED, [COCO_BIG], "c"))
    assert r.status == DETECTED
    assert r.regions == [{"rank": 0, "region": YOLO_BOX["region"], "conf": 0.8, "object_class": "bird",
                          "provider_class_id": "yolo:bird"}]


def test_coco_fallback_when_yolo_finds_nothing():
    r = combine(child(NO_DETECTION), child(DETECTED, [COCO_BIG]))
    assert r.status == DETECTED
    assert r.regions[0]["provider_class_id"] == "coco:bird"
    assert r.regions[0]["object_class"] == "animal"


def test_small_coco_box_is_refined_when_yolo_agrees():
    tight = {"region": (0.505, 0.505, 0.545, 0.548), "conf": 0.5}
    seen = []

    def refine(region):
        seen.append(region)
        return [{"region": (0.0, 0.0, 0.01, 0.01), "conf": 0.9}, tight]

    r = combine(child(NO_DETECTION), child(DETECTED, [COCO_SMALL, COCO_BIG]), refine=refine)
    assert seen == [COCO_SMALL["region"]]  # only the small box is refined (AC-10)
    assert r.regions[0]["region"] == tight["region"]
    assert r.regions[0]["provider_class_id"] == "coco+refine:bird"
    assert r.regions[1]["provider_class_id"] == "coco:bird"


def test_refine_is_rejected_below_iou_threshold():
    far = {"region": (0.9, 0.9, 0.95, 0.95), "conf": 0.9}
    r = combine(child(NO_DETECTION), child(DETECTED, [COCO_SMALL]), refine=lambda region: [far])
    assert r.regions[0]["region"] == COCO_SMALL["region"]
    assert r.regions[0]["provider_class_id"] == "coco:bird"


@pytest.mark.parametrize("y,c,want", [
    (NO_DETECTION, NO_DETECTION, NO_DETECTION),  # AC-13
    (RETRYABLE, NO_DETECTION, RETRYABLE),        # AC-14
    (NO_DETECTION, RETRYABLE, RETRYABLE),
    (TERMINAL, NO_DETECTION, TERMINAL),
    (NO_DETECTION, DISABLED, DISABLED),
    (DETECTED, NO_DETECTION, NO_DETECTION),      # a detected run without boxes carries no region
])
def test_status_combinations_without_regions(y, c, want):
    assert combine(child(y), child(c)).status == want


def test_config_hash_covers_both_children_and_refine_policy():
    base = cascade_config_hash("y", "c", 0.02)
    assert base != cascade_config_hash("y2", "c", 0.02)
    assert base != cascade_config_hash("y", "c2", 0.02)
    assert base != cascade_config_hash("y", "c", 0.03)
    assert combine(child(NO_DETECTION, h="y"), child(NO_DETECTION, h="c")).config_hash == base


def test_refine_crop_pads_and_clamps():
    assert refine_crop((0.4, 0.4, 0.5, 0.5)) == pytest.approx((0.3, 0.3, 0.6, 0.6))
    assert refine_crop((0.0, 0.0, 0.1, 0.1)) == pytest.approx((0.0, 0.0, 0.2, 0.2))
    assert iou((0, 0, 1, 1), (0, 0, 1, 1)) == 1.0
