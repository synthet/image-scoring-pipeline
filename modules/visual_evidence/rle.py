"""Binary mask run-length encoding for evidence sidecars."""

from __future__ import annotations

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
    run_val = bool(flat[0])
    run_len = 1
    for v in flat[1:]:
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
    total = width * height
    out = np.zeros(total, dtype=bool)
    idx = 0
    val = False
    for c in counts:
        if c <= 0:
            continue
        end = min(idx + c, total)
        if val:
            out[idx:end] = True
        idx = end
        val = not val
        if idx >= total:
            break
    return out.reshape((height, width), order="C")
