"""
Integration tests for Selection workflow.

Requires: database with scored images, clustering dependencies.
Run with: pytest tests/test_selection_integration.py -v
Skip if DB unavailable or no test folder.
"""

import os
import pytest
from modules.selection import SelectionService, SelectionConfig, SelectionSummary
from modules.selection_policy import classify_sorted_ids, band_sizes


def test_selection_service_run_empty_path():
    """Empty path returns error summary."""
    svc = SelectionService()
    cfg = SelectionConfig()
    summary = svc.run("", cfg=cfg)
    assert "error" in summary.status.lower()
    assert summary.total_images == 0


def test_selection_service_run_nonexistent_path():
    """Nonexistent path returns error."""
    svc = SelectionService()
    cfg = SelectionConfig()
    summary = svc.run("/nonexistent/path/xyz", cfg=cfg)
    assert "error" in summary.status.lower() or "not found" in summary.status.lower()
    assert summary.total_images == 0


@pytest.mark.skipif(
    not os.environ.get("RUN_SELECTION_INTEGRATION"),
    reason="Set RUN_SELECTION_INTEGRATION=1 to run (requires DB + scored images)",
)
def test_selection_service_full_run():
    """Full run on folder with scored images (integration)."""
    test_folder = os.environ.get("SELECTION_TEST_FOLDER", "")
    if not test_folder or not os.path.exists(test_folder):
        pytest.skip("SELECTION_TEST_FOLDER not set or folder missing")
    svc = SelectionService()
    cfg = SelectionConfig(force_rescan=False)
    log_lines = []
    def progress(pct, msg):
        log_lines.append((pct, msg))
    summary = svc.run(test_folder, cfg=cfg, progress_cb=progress)
    assert summary.total_images >= 0
    assert summary.picked + summary.rejected + summary.neutral == summary.total_images or summary.total_images == 0


@pytest.mark.skipif(
    not os.environ.get("RUN_SELECTION_INTEGRATION"),
    reason="Set RUN_SELECTION_INTEGRATION=1 to run",
)
def test_selection_idempotency():
    """Running same folder twice produces same decisions."""
    test_folder = os.environ.get("SELECTION_TEST_FOLDER", "")
    if not test_folder or not os.path.exists(test_folder):
        pytest.skip("SELECTION_TEST_FOLDER not set or folder missing")
    svc = SelectionService()
    cfg = SelectionConfig(force_rescan=True)
    s1 = svc.run(test_folder, cfg=cfg)
    s2 = svc.run(test_folder, cfg=SelectionConfig(force_rescan=False))
    assert s1.picked == s2.picked
    assert s1.rejected == s2.rejected
    assert s1.neutral == s2.neutral
