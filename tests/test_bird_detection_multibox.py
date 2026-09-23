"""Multi-box detection and deterministic ranking (issue #375, AC-6).

No GPU, no ultralytics: a fake model is injected into ``detector.model``, which makes
``load_model()`` return early before it would import ultralytics.

Two contracts are pinned here and they pull in opposite directions on purpose:

* ``detect_best_box`` must return **exactly** what it returns today. Its tie-break is
  ``max(..., key=conf)``, which picks the *first* of several equal-confidence boxes -- so
  the answer depends on YOLO's output order. That is a wart, but production reads
  ``images.bird_bbox`` written under it, so changing it would silently move stored boxes.
  The characterisation tests below were written and run against the unmodified method
  before any refactor, so they pin the old behaviour rather than the new.
* ``detect_boxes`` must be **deterministic**: the same set of boxes in any order yields
  the same ranked output. Geometry tie-breakers make that true.
"""

from __future__ import annotations

import itertools

import pytest
from PIL import Image

from modules.bird_detection import BirdDetector

from tests.test_bird_detection import _FakeBox, _FakeYOLO


def _det(**cfg):
    return BirdDetector(config=cfg, device="cpu")


def _img(w=100, h=100):
    return Image.new("RGB", (w, h))


# ---------------------------------------------------------------------------
# Characterisation — detect_best_box, pinned before refactoring
# ---------------------------------------------------------------------------

def test_detect_best_box_tie_returns_the_first_raw_box():
    """Equal confidences: today's max() keeps the first one YOLO emitted."""
    det = _det()
    det.model = _FakeYOLO([
        _FakeBox((60.0, 60.0, 90.0, 90.0), 0.80),
        _FakeBox((10.0, 10.0, 40.0, 40.0), 0.80),
    ])
    box = det.detect_best_box(_img())
    assert (box["x1"], box["y1"]) == (60, 60)


def test_detect_best_box_tie_order_dependence_is_preserved():
    """Swap the order and the answer swaps -- the documented wart, kept on purpose."""
    det = _det()
    det.model = _FakeYOLO([
        _FakeBox((10.0, 10.0, 40.0, 40.0), 0.80),
        _FakeBox((60.0, 60.0, 90.0, 90.0), 0.80),
    ])
    box = det.detect_best_box(_img())
    assert (box["x1"], box["y1"]) == (10, 10)


def test_detect_best_box_does_not_validate_geometry():
    """An inverted box still comes back from the legacy method -- compatibility."""
    det = _det()
    det.model = _FakeYOLO([_FakeBox((60.0, 10.0, 20.0, 40.0), 0.9)])
    box = det.detect_best_box(_img())
    assert box is not None
    assert (box["x1"], box["x2"]) == (60, 20)


def test_detect_best_box_full_payload_is_unchanged():
    """Pinned from observed output. Note area_frac uses the *unrounded* floats
    (39.8 * 39.2 / 10000), not the rounded integer coordinates it returns."""
    det = _det()
    det.model = _FakeYOLO([_FakeBox((20.4, 20.6, 60.2, 59.8), 0.87654)])
    assert det.detect_best_box(_img()) == {
        "x1": 20, "y1": 21, "x2": 60, "y2": 60,
        "conf": 0.8765, "img_w": 100, "img_h": 100, "area_frac": 0.156016,
    }


# ---------------------------------------------------------------------------
# detect_boxes / rank_boxes — deterministic, validated, capped
# ---------------------------------------------------------------------------

_BOXES = [
    ((10.0, 10.0, 30.0, 30.0), 0.80),
    ((60.0, 60.0, 90.0, 90.0), 0.80),   # ties the first on confidence
    ((40.0, 5.0, 55.0, 25.0), 0.80),    # three-way tie, lower y1 than both
    ((5.0, 50.0, 25.0, 70.0), 0.95),
    ((70.0, 10.0, 95.0, 35.0), 0.40),
]


def _coords(ranked):
    return [(b["x1"], b["y1"], b["x2"], b["y2"]) for b in ranked]


def test_detect_boxes_ranks_by_confidence_then_geometry():
    det = _det()
    det.model = _FakeYOLO([_FakeBox(c, s) for c, s in _BOXES])
    ranked = det.detect_boxes(_img())
    assert [b["rank"] for b in ranked] == [0, 1, 2, 3, 4]
    assert [b["conf"] for b in ranked] == [0.95, 0.80, 0.80, 0.80, 0.40]
    # The three 0.80 ties order by (y1, x1): (40,5) then (10,10) then (60,60).
    assert _coords(ranked)[1:4] == [(40, 5, 55, 25), (10, 10, 30, 30), (60, 60, 90, 90)]


def test_detect_boxes_is_invariant_to_model_output_order():
    """AC-6: every permutation of the raw boxes yields the same ranking.

    This is the property detect_best_box lacks -- its tie-break depends on the order the
    model happened to emit boxes in.
    """
    reference = None
    for perm in itertools.permutations(_BOXES):
        det = _det()
        det.model = _FakeYOLO([_FakeBox(c, s) for c, s in perm])
        got = _coords(det.detect_boxes(_img()))
        if reference is None:
            reference = got
        assert got == reference, f"order-dependent for permutation {perm}"


def test_detect_boxes_caps_at_max_det():
    det = _det(max_det=3)
    det.model = _FakeYOLO([_FakeBox(c, s) for c, s in _BOXES])
    ranked = det.detect_boxes(_img())
    assert len(ranked) == 3
    assert ranked[0]["conf"] == 0.95


def test_detect_boxes_keeps_more_than_one_box():
    """The point of AC-6: detect_best_box discards all but one of these."""
    det = _det()
    det.model = _FakeYOLO([_FakeBox(c, s) for c, s in _BOXES])
    assert len(det.detect_boxes(_img())) == len(_BOXES)
    det.model = _FakeYOLO([_FakeBox(c, s) for c, s in _BOXES])
    assert det.detect_best_box(_img()) is not None  # still exactly one


@pytest.mark.parametrize("coords", [
    (60.0, 10.0, 20.0, 40.0),     # inverted x
    (10.0, 10.0, 10.0, 40.0),     # zero width
    (-5.0, 10.0, 40.0, 40.0),     # off the left edge
    (10.0, 10.0, 140.0, 40.0),    # past the right edge
])
def test_detect_boxes_drops_unusable_geometry(coords):
    """Rejected, never clamped -- clamping would invent a box nobody detected."""
    det = _det()
    det.model = _FakeYOLO([_FakeBox(coords, 0.99), _FakeBox((20.0, 20.0, 40.0, 40.0), 0.5)])
    ranked = det.detect_boxes(_img())
    assert _coords(ranked) == [(20, 20, 40, 40)]
    assert ranked[0]["rank"] == 0


def test_near_full_frame_box_is_kept_and_flagged():
    """Recorded, not rejected: one 93% outlier is not grounds for a ceiling."""
    det = _det()
    det.model = _FakeYOLO([
        _FakeBox((1.0, 1.0, 98.0, 98.0), 0.9),
        _FakeBox((20.0, 20.0, 40.0, 40.0), 0.5),
    ])
    ranked = det.detect_boxes(_img())
    assert [b["suspicious"] for b in ranked] == [True, False]
    assert ranked[0]["area_frac"] > 0.9


def test_detect_boxes_regions_are_normalized_display_space():
    det = _det()
    det.model = _FakeYOLO([_FakeBox((50.0, 25.0, 150.0, 75.0), 0.7)])
    (box,) = det.detect_boxes(_img(200, 100))
    assert box["region"] == pytest.approx((0.25, 0.25, 0.75, 0.75))
    assert (box["img_w"], box["img_h"]) == (200, 100)


def test_detect_boxes_empty_when_nothing_found():
    det = _det()
    det.model = _FakeYOLO([])
    assert det.detect_boxes(_img()) == []
