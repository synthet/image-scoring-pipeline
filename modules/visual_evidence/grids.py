"""Focus and noise cell grids on greyscale inference renditions."""

from __future__ import annotations

import math

import numpy as np

# Starting points — re-fit on corpus (clean-room planning).
DEFAULT_FOCUS_CELL_PX = 16
DEFAULT_NOISE_CELL_PX = 20


def _laplacian_variance_cell(grey: np.ndarray) -> float:
    if grey.size < 4:
        return 0.0
    g = grey.astype(np.float64)
    lap = (
        -4 * g[1:-1, 1:-1]
        + g[0:-2, 1:-1]
        + g[2:, 1:-1]
        + g[1:-1, 0:-2]
        + g[1:-1, 2:]
    )
    return float(np.var(lap))


def _noise_sigma_cell(grey: np.ndarray) -> float:
    if grey.size < 4:
        return 0.0
    flat = grey.astype(np.float64).ravel()
    med = float(np.median(flat))
    mad = float(np.median(np.abs(flat - med)))
    return mad * 1.4826 if mad > 0 else 0.0


def _normalize_values(values: list[float]) -> list[float]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if math.isclose(lo, hi):
        return [0.5 for _ in values]
    span = hi - lo
    return [(v - lo) / span for v in values]


def build_focus_grid(
    grey: np.ndarray,
    cell_size_px: int = DEFAULT_FOCUS_CELL_PX,
    mask: np.ndarray | None = None,
) -> tuple[int, int, list[float], list[float]]:
    h, w = grey.shape
    cells_x = max(1, w // cell_size_px)
    cells_y = max(1, h // cell_size_px)
    values: list[float] = []
    for cy in range(cells_y):
        for cx in range(cells_x):
            y0, y1 = cy * cell_size_px, min(h, (cy + 1) * cell_size_px)
            x0, x1 = cx * cell_size_px, min(w, (cx + 1) * cell_size_px)
            patch = grey[y0:y1, x0:x1]
            if mask is not None and patch.size:
                m = mask[y0:y1, x0:x1]
                if m.any():
                    patch = patch[m]
                else:
                    values.append(0.0)
                    continue
            values.append(_laplacian_variance_cell(patch) if patch.size else 0.0)
    return cells_x, cells_y, values, _normalize_values(values)


def build_noise_grid(
    grey: np.ndarray,
    cell_size_px: int = DEFAULT_NOISE_CELL_PX,
    mask: np.ndarray | None = None,
) -> tuple[int, int, list[float], list[float]]:
    h, w = grey.shape
    cells_x = max(1, w // cell_size_px)
    cells_y = max(1, h // cell_size_px)
    values: list[float] = []
    for cy in range(cells_y):
        for cx in range(cells_x):
            y0, y1 = cy * cell_size_px, min(h, (cy + 1) * cell_size_px)
            x0, x1 = cx * cell_size_px, min(w, (cx + 1) * cell_size_px)
            patch = grey[y0:y1, x0:x1]
            if mask is not None and patch.size:
                m = mask[y0:y1, x0:x1]
                if m.any():
                    patch = patch[m]
                else:
                    values.append(0.0)
                    continue
            values.append(_noise_sigma_cell(patch))
    return cells_x, cells_y, values, _normalize_values(values)
