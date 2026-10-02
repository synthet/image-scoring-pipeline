"""Assemble evidence payload for an image (on-demand or fixture-backed)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from modules import db
from modules.visual_evidence import grids, rle
from modules.visual_evidence.schema import (
    CriterionBand,
    EvidenceDisplayGates,
    EvidenceGrid,
    EvidenceMaskRle,
    EvidencePayload,
    EvidenceSeparation,
)

logger = logging.getLogger(__name__)

_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "evidence" / "synthetic_orientation_1.json"


def _load_grey_from_thumbnail(path: str) -> np.ndarray | None:
    try:
        from PIL import Image
    except ImportError:
        logger.warning("PIL unavailable for evidence thumbnails")
        return None
    if not path or not os.path.isfile(path):
        return None
    try:
        with Image.open(path) as im:
            im = im.convert("L")
            return np.asarray(im, dtype=np.uint8)
    except OSError as exc:
        logger.debug("thumbnail read failed: %s", exc)
        return None


def _bbox_mask(h: int, w: int, bbox: dict[str, Any] | None) -> np.ndarray | None:
    if not bbox:
        return None
    try:
        x1 = int(bbox["x1"])
        y1 = int(bbox["y1"])
        x2 = int(bbox["x2"])
        y2 = int(bbox["y2"])
        img_w = float(bbox.get("img_w") or w)
        img_h = float(bbox.get("img_h") or h)
        sx = w / img_w if img_w else 1.0
        sy = h / img_h if img_h else 1.0
        xa = max(0, min(w, int(round(x1 * sx))))
        xb = max(0, min(w, int(round(x2 * sx))))
        ya = max(0, min(h, int(round(y1 * sy))))
        yb = max(0, min(h, int(round(y2 * sy))))
        mask = np.zeros((h, w), dtype=bool)
        if xb > xa and yb > ya:
            mask[ya:yb, xa:xb] = True
        return mask
    except (KeyError, TypeError, ValueError):
        return None


def _rendition_hash(thumbnail_path: str | None, w: int, h: int) -> str:
    base = f"{thumbnail_path or ''}:{w}x{h}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _fixture_payload(image_id: int) -> EvidencePayload | None:
    if not _FIXTURE_PATH.is_file():
        return None
    try:
        raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        raw["image_id"] = image_id
        return EvidencePayload.model_validate(raw)
    except Exception as exc:
        logger.warning("evidence fixture invalid: %s", exc)
        return None


def build_evidence_for_image(image_id: int) -> EvidencePayload:
    """Build evidence for `image_id`; uses DB thumbnail + bird_bbox when present."""
    conn = db.get_db()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT thumbnail_path, bird_bbox FROM images WHERE id = ?",
            (image_id,),
        )
        row = c.fetchone()
    finally:
        conn.close()

    if not row:
        raise KeyError(image_id)

    thumbnail_path, bird_bbox_raw = row[0], row[1]
    bbox: dict[str, Any] | None = None
    if bird_bbox_raw:
        try:
            bbox = json.loads(bird_bbox_raw) if isinstance(bird_bbox_raw, str) else bird_bbox_raw
        except json.JSONDecodeError:
            bbox = None

    grey = _load_grey_from_thumbnail(thumbnail_path or "")
    if grey is None:
        fixed = _fixture_payload(image_id)
        if fixed:
            return fixed
        return EvidencePayload(
            image_id=image_id,
            display_width=800,
            display_height=600,
            gates=EvidenceDisplayGates(),
            limitations=["no_region"],
        )

    h, w = grey.shape
    mask = _bbox_mask(h, w, bbox)
    limitations: list[str] = []
    if bbox is None:
        limitations.append("no_region")

    cx, cy, focus_vals, focus_norm = grids.build_focus_grid(grey, mask=mask)
    nx, ny, noise_vals, noise_norm = grids.build_noise_grid(grey, mask=mask)

    focus_grid = EvidenceGrid(
        cells_x=cx,
        cells_y=cy,
        cell_size_px=grids.DEFAULT_FOCUS_CELL_PX,
        values=focus_vals,
        values_normalized=focus_norm,
    )
    noise_grid = EvidenceGrid(
        cells_x=nx,
        cells_y=ny,
        cell_size_px=grids.DEFAULT_NOISE_CELL_PX,
        values=noise_vals,
        values_normalized=noise_norm,
    )

    mask_rle: EvidenceMaskRle | None = None
    if mask is not None and mask.any():
        mw, mh, counts = rle.encode_mask_rle(mask)
        mask_rle = EvidenceMaskRle(width=mw, height=mh, counts=counts)

    subj_mean = float(np.mean([focus_vals[i] for i in range(len(focus_vals))])) if focus_vals else None
    separation = EvidenceSeparation(
        subject_sharpness_mean=subj_mean,
        background_sharpness_mean=None,
        ratio=None,
        noise_sigma_mean=float(np.mean(noise_vals)) if noise_vals else None,
    )

    gates = EvidenceDisplayGates(
        region=bbox is not None,
        mask=mask_rle is not None,
        keypoints=False,
        focus_grid=True,
        noise_grid=True,
    )

    criteria = [
        CriterionBand(criterion="focus", band="acceptable" if subj_mean and subj_mean > 10 else "soft", sub_score=72),
        CriterionBand(criterion="noise", band="acceptable", sub_score=65),
    ]

    return EvidencePayload(
        image_id=image_id,
        display_width=w,
        display_height=h,
        rendition_hash=_rendition_hash(thumbnail_path, w, h),
        gates=gates,
        limitations=limitations,
        criteria=criteria,
        focus_grid=focus_grid,
        noise_grid=noise_grid,
        mask_rle=mask_rle,
        separation=separation,
        region_bbox=bbox,
    )
