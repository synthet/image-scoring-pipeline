"""Tests for scripts/analysis/export_score_analytics.py (fixture matrix, no DB)."""

import csv
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from modules.score_analytics import data

@pytest.fixture(scope="module")
def exporter():
    script = Path(__file__).resolve().parents[1] / "scripts" / "analysis" / "export_score_analytics.py"
    spec = importlib.util.spec_from_file_location("export_score_analytics", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _matrix(n=120):
    rng = np.random.default_rng(3)
    liqe, spaq = rng.random(n), rng.random(n)
    general = 0.5 * liqe + 0.5 * spaq
    image_rows = [(i + 1, float(general[i]), None, None, i // 4 + 1, 1 if i % 4 == 0 else 0) for i in range(n)]
    score_rows = [(i + 1, "liqe", float(liqe[i]), False) for i in range(n)]
    score_rows += [(i + 1, "spaq", float(spaq[i]), False) for i in range(n)]
    return data.build_matrix(image_rows, score_rows, "fp", [(1, 1)])


def test_export_all_writes_layers(tmp_path, exporter):
    m = _matrix()
    summary = exporter.export_all(
        m,
        tmp_path,
        keywords=[("bird", None), ("empty", None)],
        keyword_ids={"bird": np.arange(1, 61), "empty": np.array([], dtype=np.int64)},
        formats={"csv", "json"},
        target="general",
        predictors=None,
        min_stack_size=2,
        per_image=True,
        per_stack=True,
        file_paths={1: "/p/1.jpg"},
    )
    files = set(summary["files"])
    for rel in (
        "layers/library/per_image_scores.csv",
        "layers/library/descriptives.csv",
        "layers/library/correlations_long.csv",
        "layers/library/regression_coefficients.csv",
        "layers/library/stacks_model_signals.csv",
        "layers/library/stacks_per_stack.csv",
        "layers/keyword=bird/descriptives.csv",
        "keyword_profiles.csv",
        "summary.json",
    ):
        assert rel in files
        assert (tmp_path / rel).exists()

    assert summary["layers"]["keyword=empty"]["skipped"] == "no scored images"
    assert summary["layers"]["library"]["regression"]["r2"] > 0.999
    assert summary["layers"]["library"]["stacks"]["stacks_considered"] == 30

    with (tmp_path / "layers/library/per_image_scores.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 120
    assert rows[0]["file_path"] == "/p/1.jpg" and rows[0]["pick_status"] == "1"

    manifest = json.loads((tmp_path / "summary.json").read_text())
    assert manifest["layers"]["keyword=bird"]["images"] == 60


def test_csv_only_and_slug(tmp_path, exporter):
    exporter.export_all(
        _matrix(40), tmp_path, keywords=[], keyword_ids={}, formats={"csv"},
        target="general", predictors=["liqe"], min_stack_size=2, per_image=False, per_stack=False,
    )
    assert not list(tmp_path.glob("layers/library/*.json"))
    assert exporter.layer_slug("Blue Sky/2") == "keyword=blue_sky_2"
    assert exporter.layer_slug(None) == "library"
