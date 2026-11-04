"""Spec 08 (#780): does RTMDet confirm a bird region on its padded crop?

Pure functions, no I/O and no model. The caller runs RTMDet on the crop and passes its boxes in.
The agreement limit is applied at read time, so stored scores stay valid if the limit changes.
"""
from __future__ import annotations

import hashlib

from modules.localization_cascade import Region, iou

DETECTOR_KEY = "bird_agreement"
BIRD_CLASS = "bird"
CROP_PAD = 0.25
MIN_IOU = 0.3
#: Provider threshold: low enough that scores near AGREEMENT_LIMIT are not filtered out.
SCORE_FLOOR = 0.05
AGREEMENT_LIMIT = 0.10
MIN_CROP_PX = 8


def padded_crop(region: Region, width: int, height: int, pad: float = CROP_PAD) -> tuple[int, int, int, int] | None:
    """Pixel crop around a normalized region, padded by ``pad`` of its size per side.

    ``None`` when the crop is under ``MIN_CROP_PX`` on either side.
    """
    x1, y1, x2, y2 = region[0] * width, region[1] * height, region[2] * width, region[3] * height
    pad_x, pad_y = pad * (x2 - x1), pad * (y2 - y1)
    crop = (max(0, round(x1 - pad_x)), max(0, round(y1 - pad_y)),
            min(width, round(x2 + pad_x)), min(height, round(y2 + pad_y)))
    if crop[2] - crop[0] < MIN_CROP_PX or crop[3] - crop[1] < MIN_CROP_PX:
        return None
    return crop


def agreement_score(region: Region, crop: tuple[int, int, int, int], boxes: list[dict], width: int, height: int,
                    min_iou: float = MIN_IOU) -> float:
    """Highest bird score among ``boxes`` that overlap ``region``, or 0.0.

    ``region`` is normalized to the frame. ``crop`` is in frame pixels. ``boxes`` are RTMDet
    results for the crop, so their regions are normalized to the crop.
    """
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    best = 0.0
    for box in boxes:
        if box["cls"] != BIRD_CLASS:
            continue
        x1, y1, x2, y2 = box["region"]
        in_frame = ((crop[0] + x1 * cw) / width, (crop[1] + y1 * ch) / height,
                    (crop[0] + x2 * cw) / width, (crop[1] + y2 * ch) / height)
        if iou(region, in_frame) >= min_iou:
            best = max(best, float(box["conf"]))
    return best


def agreement_config_hash(rtmdet_config_hash: str, bird_config_hash: str, pad: float = CROP_PAD,
                          min_iou: float = MIN_IOU) -> str:
    parts = ("bird-agreement-v1", rtmdet_config_hash, bird_config_hash, f"{pad:.4f}", f"{min_iou:.4f}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
