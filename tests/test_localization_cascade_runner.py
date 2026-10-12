"""Spec 03 slice 2 (#408): the runner persists ``coco`` and ``subject_cascade`` runs in shadow."""

from types import SimpleNamespace

from PIL import Image

import modules.localization as loc
import modules.localization_cascade_runner as cr

BIRD = {"id": 5, "status": "no_detection", "detector_config_hash": "y", "source_hash": "s", "source_hash_version": "v",
        "rendition_hash": "r", "rendition_version": "1", "orientation": 1, "display_width": 1000,
        "display_height": 500, "decode_route": "raw_embedded_preview"}


class _Conn:
    def __init__(self, bird, current=None, regions=()):
        self.bird, self.current, self.regions = bird, current, list(regions)

    def query_one(self, sql, params):
        return self.bird if params[1] == "bird" else self.current

    def query(self, sql, params):
        return self.regions


class _Yolo:
    def detect_boxes(self, image):
        return [{"region": (0.25, 0.25, 0.75, 0.75), "conf": 0.8}]


def _ctx(enabled=True, boxes=()):
    rt = SimpleNamespace(enabled=enabled, version="rtmdet_tiny_coco/x.onnx", config_hash="c", error_code=None,
                         detect=lambda image: list(boxes))
    return cr.CascadeContext(rtmdet=rt, yolo=_Yolo(), yolo_config_hash="y", refine_area_frac=0.02)


def _setup(monkeypatch, conn):
    writes = []
    monkeypatch.setattr("modules.db.get_connector", lambda: conn, raising=False)
    monkeypatch.setattr(loc, "write_run", lambda run, regions, publish=True: writes.append((run, regions)) or 1)
    monkeypatch.setattr(loc, "decode_for_localization", lambda path: SimpleNamespace(
        image=Image.new("RGB", (1000, 500)), descriptor=SimpleNamespace(rendition_hash="r")))
    return writes


def test_disabled_flag_builds_no_context():
    """AC-15: no cascade context, so no coco / subject_cascade runs."""
    ctx = SimpleNamespace(enabled=True, load_error=None, detector=object(), config_hash="y")
    assert cr.load_cascade_context({}, ctx) is None
    assert cr.load_cascade_context({"cascade": {"enabled": False}}, ctx) is None


def test_detected_bird_run_adopts_yolo_boxes_without_rtmdet(monkeypatch):
    bird = dict(BIRD, status="detected")
    writes = _setup(monkeypatch, _Conn(bird, regions=[{"rank": 0, "x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.4,
                                                       "confidence": 0.9}]))
    called = []
    ctx = _ctx()
    ctx.rtmdet.detect = lambda image: called.append(1) or []
    assert cr.localize_cascade(1, "a.nef", ctx, max_regions=10) == "detected"
    assert not called and len(writes) == 1
    run, regions = writes[0]
    assert run["detector_key"] == "subject_cascade" and run["rendition_hash"] == "r"
    assert regions[0]["provider_class_id"] == "yolo:bird"


def test_no_detection_runs_coco_persists_child_and_refines_small_box(monkeypatch):
    small = {"region": (0.4, 0.4, 0.45, 0.45), "conf": 0.7, "cls": "bird"}
    writes = _setup(monkeypatch, _Conn(BIRD))
    assert cr.localize_cascade(1, "a.nef", _ctx(boxes=[small]), max_regions=10) == "detected"
    (coco_run, coco_regions), (run, regions) = writes
    assert coco_run["detector_key"] == "coco" and coco_regions[0]["provider_class_id"] == "coco:bird"  # AC-6
    assert regions[0]["provider_class_id"] == "coco+refine:bird"  # AC-10/11


def test_coco_failure_is_retryable(monkeypatch):
    writes = _setup(monkeypatch, _Conn(BIRD))
    ctx = _ctx()
    ctx.rtmdet.detect = lambda image: (_ for _ in ()).throw(RuntimeError("onnx"))
    assert cr.localize_cascade(1, "a.nef", ctx, max_regions=10) == "retryable_error"  # AC-14
    assert [w[0]["detector_key"] for w in writes] == ["subject_cascade"]


def test_unchanged_identity_writes_nothing(monkeypatch):
    from modules.localization_cascade import cascade_config_hash

    current = {"status": "no_detection", "detector_config_hash": cascade_config_hash("y", "c", 0.02),
               "rendition_hash": "r", "source_hash": "s"}
    writes = _setup(monkeypatch, _Conn(BIRD, current=current))
    assert cr.localize_cascade(1, "a.nef", _ctx(), max_regions=10) is None
    assert writes == []
