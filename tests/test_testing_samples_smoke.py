"""Lightweight checks on ``D:\\Photos\\TestingSamples`` (no Firebird)."""

from __future__ import annotations

import os

import pytest

from tests.support.testing_samples import list_sample_image_files, testing_samples_root

pytestmark = pytest.mark.sample_data


def test_testing_samples_root_lists_files_or_skip():
    """When root exists, at least one supported image file is present."""
    paths = list_sample_image_files()
    root = testing_samples_root()
    if not os.path.isdir(root):
        pytest.skip(f"TestingSamples root not found: {root}")
    assert len(paths) >= 1, (
        f"Expected image files under {root}; none found. "
        "Run scripts/python/download_nef_testing_samples.py per NEF_TESTING_SAMPLES_URLS.md"
    )


def test_nef_samples_decode_with_rawpy_when_installed():
    """Optional: same check as verify_nef_testing_samples.py (no DB)."""
    nef_paths = [p for p in list_sample_image_files() if p.lower().endswith(".nef")]
    root = testing_samples_root()
    if not os.path.isdir(root):
        pytest.skip(f"TestingSamples root not found: {root}")
    if not nef_paths:
        pytest.skip("No .NEF files under TestingSamples")

    rawpy = pytest.importorskip("rawpy")
    with rawpy.imread(nef_paths[0]) as raw:
        assert raw.sizes.width > 0 and raw.sizes.height > 0
