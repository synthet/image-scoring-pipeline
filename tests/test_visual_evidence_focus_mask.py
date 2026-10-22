"""Subject masks select Laplacian samples without destroying pixel neighborhoods."""
import numpy as np
import pytest

from modules.visual_evidence.grids import build_focus_grid


@pytest.mark.parametrize('mask_kind', ['full', 'left', 'empty'])
def test_masked_focus_matches_spatial_laplacian_samples(mask_kind):
    grey = np.zeros((8, 8), dtype=np.uint8)
    grey[3, 4] = 200
    grey[4, 5] = 100
    mask = np.zeros_like(grey, dtype=bool)
    if mask_kind == 'full':
        mask[:] = True
    elif mask_kind == 'left':
        mask[:, :4] = True
    samples = []
    for y in range(1, 7):
        for x in range(1, 7):
            if mask[y, x]:
                samples.append(-4*int(grey[y, x]) + int(grey[y-1, x]) + int(grey[y+1, x])
                               + int(grey[y, x-1]) + int(grey[y, x+1]))
    expected = float(np.var(samples)) if samples else 0.0
    cx, cy, values, normalized = build_focus_grid(grey, cell_size_px=8, mask=mask)
    assert (cx, cy) == (1, 1)
    assert values == pytest.approx([expected])
    assert normalized == [0.5]


@pytest.mark.parametrize('shape', [(1, 8), (2, 8), (8, 1), (8, 2)])
def test_cells_without_a_laplacian_neighborhood_are_finite_zero(shape):
    _, _, values, normalized = build_focus_grid(np.ones(shape, dtype=np.uint8), cell_size_px=16)
    assert values == [0.0]
    assert normalized == [0.5]
