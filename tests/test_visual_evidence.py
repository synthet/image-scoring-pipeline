"""Visual evidence grids, RLE, and API payload assembly."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from modules.visual_evidence.grids import build_focus_grid, build_noise_grid
from modules.visual_evidence.rle import decode_mask_rle, encode_mask_rle
from modules.visual_evidence.schema import EvidencePayload
from modules.visual_evidence.service import build_evidence_for_image


def test_focus_grid_shape_and_normalize():
    grey = np.linspace(0, 255, 64 * 48, dtype=np.uint8).reshape(48, 64)
    cx, cy, values, norm = build_focus_grid(grey, cell_size_px=16)
    assert cx == 4 and cy == 3
    assert len(values) == cx * cy
    assert len(norm) == len(values)
    assert min(norm) >= 0.0 and max(norm) <= 1.0


def test_rle_roundtrip():
    mask = np.zeros((6, 8), dtype=bool)
    mask[1:5, 2:6] = True
    w, h, counts = encode_mask_rle(mask, max_dim=256)
    back = decode_mask_rle(w, h, counts)
    assert back.shape == mask.shape
    assert np.array_equal(back, mask)


def test_fixture_validates():
    path = Path(__file__).parent / "fixtures" / "evidence" / "synthetic_orientation_1.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    payload = EvidencePayload.model_validate(raw)
    assert payload.gates.focus_grid is True


def test_build_evidence_missing_image():
    with pytest.raises(KeyError):
        build_evidence_for_image(-1)
