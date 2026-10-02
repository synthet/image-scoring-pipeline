"""Unit tests for modules.score_analytics.model_selection (synthetic data, no DB)."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from modules import score_normalization as sn
from modules.score_analytics import data
from modules.score_analytics import model_selection as ms

ANCHORS = {m: {"p02": 0.0, "p98": 1.0} for m in ("liqe", "spaq", "topiq", "arniqa", "ava")}
RATING = {5: 0.9, 4: 0.72, 3: 0.5, 2: 0.3}
LABEL = dict(sn.DEFAULT_LABEL_THRESHOLDS)


def _world(n_stacks=150, size=5, singles=150, seed=0):
    """Scene + frame quality; models see it with different noise."""
    rng = np.random.default_rng(seed)
    n = n_stacks * size + singles
    stack_ids = np.r_[np.repeat(np.arange(1, n_stacks + 1), size), np.zeros(singles, dtype=np.int64)]
    scene = np.r_[np.repeat(rng.normal(0, 1, n_stacks), size), rng.normal(0, 1, singles)]
    truth = scene + rng.normal(0, 1, n)

    def seen(noise):
        return np.clip(0.5 + 0.12 * (truth + noise * rng.normal(0, 1, n)), 0, 1)

    series = {
        "liqe": seen(0.3),
        "spaq": seen(0.6),
        "topiq": seen(0.6),
        "arniqa": np.clip(0.5 + 0.12 * rng.normal(0, 1, n), 0, 1),
        "ava": np.clip(0.5 + 0.12 * scene, 0, 1),
    }
    return series, stack_ids


def _matrix(series, stack_ids, composites=None):
    n = stack_ids.size
    comp = composites or {}
    image_rows = [
        (i + 1, *(None if comp.get(c) is None else float(comp[c][i]) for c in data.COMPOSITE_KEYS), int(stack_ids[i]), 0)
        for i in range(n)
    ]
    score_rows = [
        (i + 1, name, float(v[i]), name.startswith("refcull_"))
        for name, v in series.items()
        for i in range(n)
        if np.isfinite(v[i])
    ]
    return data.build_matrix(image_rows, score_rows, "fp")


def _report(series, stack_ids, weights, composites=None):
    return ms.build_report(
        _matrix(series, stack_ids, composites),
        weights=weights,
        anchors=ANCHORS,
        rating_thresholds=RATING,
        label_thresholds=LABEL,
        bootstrap=20,
    )


def _verdict(rows, model):
    return next(r for r in rows if r["model"] == model)


def test_ablation_zero_weight_is_identity():
    series, stack_ids = _world()
    weights = {"general": {"liqe": 0.5, "spaq": 0.5, "arniqa": 0.0}}
    rows = ms.composite_ablation(series, weights, ANCHORS, RATING, LABEL, stack_ids)
    row = next(r for r in rows if r["composite"] == "general" and r["model"] == "arniqa")
    assert row["spearman"] == pytest.approx(1.0)
    assert row["rating_change"] == 0.0
    assert row["label_change"] == 0.0
    assert row["top_overlap"] == pytest.approx(1.0)
    assert row["best_frame_change"] == 0.0


def test_ablation_matches_compute_composites_when_model_missing(monkeypatch):
    monkeypatch.setattr(sn, "_load_config", lambda: {})
    rng = np.random.default_rng(7)
    n = 60
    series = {m: rng.random(n) for m in sn.DEFAULT_PERCENTILE_ANCHORS}
    series["topiq"][::3] = np.nan
    series["arniqa"][1::4] = np.nan
    weights = sn.DEFAULT_COMPOSITE_WEIGHTS
    anchors = sn.DEFAULT_PERCENTILE_ANCHORS
    comp = {c: ms.composite_score(series, weights[c], anchors) for c in weights}
    rating = ms.ratings(comp["general"], sn.DEFAULT_RATING_THRESHOLDS)
    label = ms.labels(comp["technical"], comp["aesthetic"], sn.DEFAULT_LABEL_THRESHOLDS)
    for i in range(n):
        scores = {m: float(v[i]) for m, v in series.items() if np.isfinite(v[i])}
        expected = sn.compute_composites(scores)
        for c in weights:
            assert comp[c][i] == pytest.approx(expected[c], abs=1e-9)
        assert rating[i] == sn.score_to_rating(expected["general"])
        assert label[i] == sn.determine_label(scores)


def test_duplicate_model_flagged_redundant():
    series, stack_ids = _world()
    series["topiq"] = np.clip(series["liqe"] + 0.002 * np.random.default_rng(1).normal(size=stack_ids.size), 0, 1)
    rep = _report(series, stack_ids, {"general": {"liqe": 0.5, "spaq": 0.3, "topiq": 0.2}})
    within = rep["redundancy"]["within"]
    assert any({"liqe", "topiq"} <= set(g["members"]) for g in within)
    culling = rep["verdicts"]["culling"]
    pair = {_verdict(culling, "liqe")["verdict"], _verdict(culling, "topiq")["verdict"]}
    assert "omittable" in pair


def test_noise_model_low_stack_consensus():
    series, stack_ids = _world()
    res = ms.stack_consensus(series, ["liqe", "spaq", "topiq", "arniqa"], stack_ids, bootstrap=20)
    assert abs(res["models"]["arniqa"]["kendall_tau_b"]) < 0.1
    assert res["models"]["liqe"]["kendall_tau_b"] > 0.3
    lo, hi = res["models"]["liqe"]["kendall_tau_b_ci"]
    assert lo <= res["models"]["liqe"]["kendall_tau_b"] <= hi


def test_tie_heavy_model_omittable_for_culling():
    series, stack_ids = _world()
    rep = _report(series, stack_ids, {"general": {"liqe": 0.5, "spaq": 0.3, "ava": 0.2}})
    ava = _verdict(rep["verdicts"]["culling"], "ava")
    assert ava["verdict"] == "omittable"
    assert any("tie" in r for r in ava["reasons"])


def test_forward_select_stops_below_gain():
    table = {frozenset("a"): 0.5, frozenset("b"): 0.4, frozenset("c"): 0.1,
             frozenset("ab"): 0.7, frozenset("ac"): 0.55, frozenset("abc"): 0.705}
    res = ms.forward_select(["a", "b", "c"], lambda s: table[frozenset(s)], max_models=3, min_gain=0.01)
    assert res["selected"] == ["a", "b"]
    assert [s["score"] for s in res["steps"]] == pytest.approx([0.5, 0.7])
    assert "gain" in res["stop_reason"]


def test_partial_coverage_uses_common_support():
    series, stack_ids = _world()
    partial = series["spaq"].copy()
    partial[(stack_ids % 2 == 1) | (stack_ids == 0)] = np.nan
    series["koniq"] = partial
    full = ms.stack_consensus(series, ["liqe", "spaq", "topiq"], stack_ids, bootstrap=10)
    with_partial = ms.stack_consensus(series, ["liqe", "spaq", "topiq", "koniq"], stack_ids, bootstrap=10)
    assert full["stacks"] == 150
    assert with_partial["stacks"] == 75
    assert with_partial["images"] == 75 * 5


def test_derived_family_excluded_from_verdicts():
    series, stack_ids = _world()
    series["refcull_composite"] = series["liqe"].copy()
    series["koniq"] = series["spaq"].copy()
    general = 0.5 * series["liqe"] + 0.5 * series["spaq"]
    rep = _report(series, stack_ids, {"general": {"liqe": 0.5, "spaq": 0.5}}, {"general": general})
    assert rep["roles"]["refcull_composite"] == "research_family"
    assert rep["roles"]["koniq"] == "legacy"
    assert rep["roles"]["general"] == "composite"
    judged = {r["model"] for rows in rep["verdicts"].values() for r in rows}
    assert judged.isdisjoint({"refcull_composite", "koniq", "general"})
    assert "refcull_composite" in rep["correlation"]["keys"]


def test_report_script_writes_outputs(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "analysis" / "model_selection_report.py"
    spec = importlib.util.spec_from_file_location("model_selection_report", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    series, stack_ids = _world()
    weights = {"general": {"liqe": 0.4, "spaq": 0.3, "topiq": 0.2, "ava": 0.1},
               "technical": {"topiq": 0.5, "liqe": 0.5}, "aesthetic": {"ava": 0.5, "spaq": 0.5}}
    m = _matrix(series, stack_ids)
    rep = _report(series, stack_ids, weights)
    costs = {"table": mod.COST_TABLE, "observed": {"available": False, "note": "not persisted"}, "estimated": True}
    files = mod.write_report(rep, mod.manifest(m, {"min_size": 2}), costs, m, tmp_path, {"csv", "json"}, charts=True)
    assert {"REPORT.md", "verdicts.csv", "ablation.csv", "report.json", "charts/stack_signals.svg"} <= set(files)
    text = (tmp_path / "REPORT.md").read_text(encoding="utf-8")
    assert ms.CAVEAT in text
    assert "### culling" in text and "### general" in text
    assert (tmp_path / "charts" / "ablation_general.svg").read_text(encoding="utf-8").startswith("<svg")
