"""Assemble legacy evidence from real, display-oriented preview pixels."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import numpy as np

from modules import db
from modules.localization_legacy import overlay_bird_bboxes
from modules.paths import resolve_to_existing
from modules.visual_evidence import grids
from modules.visual_evidence.schema import (
    EvidenceDisplayGates,
    EvidenceGrid,
    EvidencePayload,
    EvidenceSeparation,
)

logger = logging.getLogger(__name__)



def _load_grey_from_thumbnail(path: str) -> np.ndarray | None:
    path = resolve_to_existing(path)
    try:
        from PIL import Image, ImageOps
    except ImportError:
        logger.warning("PIL unavailable for evidence thumbnails")
        return None
    if not path or not os.path.isfile(path):
        return None
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("L")
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
    from modules.rendition import source_identity

    identity, version = source_identity(resolve_to_existing(thumbnail_path) or thumbnail_path)
    base = f"{identity}:{version}:{w}x{h}:legacy_oriented_v2"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


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
    image_row = {"id": image_id, "bird_bbox": bird_bbox_raw}
    overlay_bird_bboxes([image_row])
    bird_bbox_raw = image_row["bird_bbox"]
    bbox: dict[str, Any] | None = None
    if bird_bbox_raw:
        try:
            bbox = json.loads(bird_bbox_raw) if isinstance(bird_bbox_raw, str) else bird_bbox_raw
        except json.JSONDecodeError:
            bbox = None

    grey = _load_grey_from_thumbnail(thumbnail_path or "")
    if grey is None:
        return EvidencePayload(
            image_id=image_id,
            display_width=1,
            display_height=1,
            gates=EvidenceDisplayGates(),
            limitations=["source_unavailable"],
        )

    h, w = grey.shape
    limitations: list[str] = []
    if bbox is None:
        limitations.append("no_region")

    cx, cy, focus_vals, focus_norm = grids.build_focus_grid(grey)
    nx, ny, noise_vals, noise_norm = grids.build_noise_grid(grey)

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

    separation = EvidenceSeparation(
        subject_sharpness_mean=None,
        background_sharpness_mean=None,
        ratio=None,
        noise_sigma_mean=float(np.mean(noise_vals)) if noise_vals else None,
    )

    gates = EvidenceDisplayGates(
        region=bbox is not None,
        mask=False,
        keypoints=False,
        focus_grid=True,
        noise_grid=True,
    )

    return EvidencePayload(
        image_id=image_id,
        display_width=w,
        display_height=h,
        rendition_hash=_rendition_hash(thumbnail_path, w, h),
        gates=gates,
        limitations=limitations,
        criteria=[],
        focus_grid=focus_grid,
        noise_grid=noise_grid,
        mask_rle=None,
        separation=separation,
        region_bbox=bbox,
    )
