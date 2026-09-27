"""Subject cascade: YOLO bird boxes first, COCO animal fallback, small-box YOLO refine (spec 03, #408).

A pure combination of the two child providers' outcomes -- no I/O, no model. The caller runs the
children (and supplies ``refine`` when pixels are at hand) and persists the result as a
``subject_cascade`` localization run.

Every adopted region records the step that produced it in ``provider_class_id`` (AC-12):
``yolo:bird``, ``coco:<class>`` or ``coco+refine:<class>``.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable

DETECTOR_KEY = "subject_cascade"
COCO_DETECTOR_KEY = "coco"
DEFAULT_REFINE_AREA_FRAC = 0.02
REFINE_PAD_FRAC = 1.0
REFINE_MIN_IOU = 0.3

DETECTED = "detected"
NO_DETECTION = "no_detection"
RETRYABLE = "retryable_error"
TERMINAL = "terminal_error"
DISABLED = "disabled"

Region = tuple[float, float, float, float]


@dataclass
class ChildOutcome:
    """One child provider's answer for an image: its status and ranked ``{"region", "conf", ...}`` boxes."""

    status: str
    config_hash: str
    boxes: list[dict] = field(default_factory=list)


@dataclass
class CascadeResult:
    status: str
    regions: list[dict]
    config_hash: str


def iou(a: Region, b: Region) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u > 0 else 0.0


def refine_crop(region: Region, pad_frac: float = REFINE_PAD_FRAC) -> Region:
    """Normalized crop around ``region`` padded by ``pad_frac`` of its size per side (policy ``refine_v1``)."""
    x1, y1, x2, y2 = region
    w, h = x2 - x1, y2 - y1
    return (max(0.0, x1 - pad_frac * w), max(0.0, y1 - pad_frac * h),
            min(1.0, x2 + pad_frac * w), min(1.0, y2 + pad_frac * h))


def cascade_config_hash(yolo_hash: str, coco_hash: str, refine_area_frac: float) -> str:
    """AC-7: covers both children's config hashes and the refine policy."""
    parts = ("cascade-v1", yolo_hash, coco_hash, f"{refine_area_frac:.4f}", f"{REFINE_PAD_FRAC:.2f}",
             f"{REFINE_MIN_IOU:.2f}")
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def combine(yolo: ChildOutcome, coco: ChildOutcome, *, refine: Callable[[Region], list[dict]] | None = None,
            refine_area_frac: float = DEFAULT_REFINE_AREA_FRAC) -> CascadeResult:
    """Combine the child outcomes (AC-8 to AC-14).

    ``refine(region)`` runs YOLO on the padded crop of a small COCO box and returns its boxes as
    ``{"region", "conf"}`` in **frame**-normalized coordinates; ``None`` skips the refine pass.
    """
    config_hash = cascade_config_hash(yolo.config_hash, coco.config_hash, refine_area_frac)

    if yolo.status == DETECTED and yolo.boxes:  # AC-8
        regions = [{"rank": r, "region": tuple(b["region"]), "conf": b["conf"], "object_class": "bird",
                    "provider_class_id": "yolo:bird"} for r, b in enumerate(yolo.boxes)]
        return CascadeResult(DETECTED, regions, config_hash)

    if coco.status == DETECTED and coco.boxes:  # AC-9
        regions = []
        for r, b in enumerate(coco.boxes):
            region, conf, step = tuple(b["region"]), b["conf"], "coco"
            area = (region[2] - region[0]) * (region[3] - region[1])
            if refine is not None and area < refine_area_frac:  # AC-10
                best = max(refine(region) or [], key=lambda rb: iou(tuple(rb["region"]), region), default=None)
                if best is not None and iou(tuple(best["region"]), region) >= REFINE_MIN_IOU:  # AC-11
                    region, conf, step = tuple(best["region"]), best["conf"], "coco+refine"
            regions.append({"rank": r, "region": region, "conf": conf, "object_class": "animal",
                            "provider_class_id": f"{step}:{b.get('cls', 'animal')}"})
        return CascadeResult(DETECTED, regions, config_hash)

    statuses = {yolo.status, coco.status}
    if RETRYABLE in statuses:  # AC-14
        return CascadeResult(RETRYABLE, [], config_hash)
    if statuses <= {NO_DETECTION, DETECTED}:  # AC-13 (DETECTED with no boxes is a no_detection)
        return CascadeResult(NO_DETECTION, [], config_hash)
    if TERMINAL in statuses:
        return CascadeResult(TERMINAL, [], config_hash)
    return CascadeResult(DISABLED, [], config_hash)
