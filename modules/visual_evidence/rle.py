"""Binary mask run-length encoding for evidence sidecars."""

from __future__ import annotations

from numbers import Integral

import numpy as np


def encode_mask_rle(mask: np.ndarray, max_dim: int = 256) -> tuple[int, int, list[int]]:
    """Encode a boolean H×W mask; downsample so max(H,W) <= max_dim (starting point)."""
    if mask.dtype != np.bool_:
        mask = mask.astype(bool)
    h, w = mask.shape
    scale = 1.0
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        # Nearest-neighbour downsample without cv2 dependency.
        ys = (np.arange(new_h) / scale).astype(int).clip(0, h - 1)
        xs = (np.arange(new_w) / scale).astype(int).clip(0, w - 1)
        mask = mask[ys[:, None], xs[None, :]]
        h, w = mask.shape
    flat = mask.flatten(order="C")
    counts: list[int] = []
    if flat.size == 0:
        return w, h, counts
    run_val = False
    run_len = 0
    for v in flat:
        vb = bool(v)
        if vb == run_val:
            run_len += 1
        else:
            counts.append(run_len)
            run_val = vb
            run_len = 1
    counts.append(run_len)
    return w, h, counts


def decode_mask_rle(width: int, height: int, counts: list[int]) -> np.ndarray:
    if not isinstance(width, Integral) or not isinstance(height, Integral) or width <= 0 or height <= 0:
        raise ValueError("Mask dimensions must be positive integers")
    total = width * height
    if any(not isinstance(count, Integral) or isinstance(count, bool) or count < 0 for count in counts):
        raise ValueError("Mask counts must be non-negative integers")
    if sum(counts) != total:
        raise ValueError("Mask counts must exactly cover the raster")
    out = np.zeros(total, dtype=bool)
    idx = 0
    val = False
    for count in counts:
        end = idx + count
        if val:
            out[idx:end] = True
        idx = end
        val = not val
    return out.reshape((height, width), order="C")
