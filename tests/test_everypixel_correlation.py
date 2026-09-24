"""Tests for Everypixel correlation join/analysis (no DB, no network)."""

from __future__ import annotations

from scripts.research.everypixel_correlation.join_and_analyze import (
    build_joined_rows,
    correlation_table,
)
from scripts.research.everypixel_correlation.statistical_modeling import (
    ols_fit,
    run_modeling_suite,
)


def _synthetic_joined():
    return [
        {
            "ugc_class": 5,
            "ugc_score": 0.9,
            "score_general": 0.85,
            "score_technical": 0.8,
            "score_aesthetic": 0.7,
            "liqe": 0.75,
            "spaq": 0.8,
            "ava": 0.6,
            "topiq": 0.7,
            "arniqa": 0.72,
            "rating": 5,
        },
        {
            "ugc_class": 4,
            "ugc_score": 0.7,
            "score_general": 0.65,
            "score_technical": 0.6,
            "score_aesthetic": 0.55,
            "liqe": 0.55,
            "spaq": 0.6,
            "ava": 0.5,
            "topiq": 0.52,
            "arniqa": 0.58,
            "rating": 4,
        },
        {
            "ugc_class": 2,
            "ugc_score": 0.3,
            "score_general": 0.35,
            "score_technical": 0.4,
            "score_aesthetic": 0.3,
            "liqe": 0.4,
            "spaq": 0.35,
            "ava": 0.32,
            "topiq": 0.38,
            "arniqa": 0.41,
            "rating": 2,
        },
    ]


def test_correlation_table_on_synthetic_rows():
    joined = _synthetic_joined()
    table = correlation_table(joined)
    by_key = {(r["target"], r["feature"]): r for r in table}
    assert by_key[("ugc_class", "score_general")]["n"] == 3
    assert float(by_key[("ugc_class", "score_general")]["spearman_r"]) > 0.9


def test_ols_fit_perfect_linear_relationship():
    import numpy as np

    x = np.linspace(0.2, 0.8, 30)
    y = 0.2 + 0.9 * x
    X = x.reshape(-1, 1)
    m = ols_fit(y, X, ["x"])
    assert m["r2"] > 0.99
    assert m["coefficients"][1]["term"] == "x"


def test_modeling_suite_returns_vif_and_regression():
    suite = run_modeling_suite(_synthetic_joined())
    assert len(suite["descriptive"]) >= 3
    assert len(suite["predictor_correlations"]) >= 1


def test_build_joined_rows_merges_manifest_and_models():
    manifest = {
        "images": [
            {"image_id": 1, "score_general": 0.5, "score_technical": 0.4, "score_aesthetic": 0.3},
        ]
    }
    ugc = [{"image_id": 1, "status": "ok", "ugc_score": 0.5, "ugc_class": 3}]
    models = {1: {"liqe": 0.42}}
    joined = build_joined_rows(manifest, ugc, models)
    assert len(joined) == 1
    assert joined[0]["ugc_class"] == 3
    assert joined[0]["liqe"] == 0.42


def test_resolve_reports_dir_env_override(monkeypatch, tmp_path):
    from scripts.research.everypixel_correlation import common

    monkeypatch.setenv("EVERYPIXEL_CORRELATION_DIR", str(tmp_path / "custom"))
    assert common.resolve_reports_dir() == (tmp_path / "custom").resolve()
