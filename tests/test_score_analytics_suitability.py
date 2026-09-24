"""Tests for the global-vs-cluster suitability toolkit (pure; synthetic ground truth, no DB)."""

import json

import numpy as np
import pytest

from modules.score_analytics import data, labels, suitability as su, suitability_report as sr


def _synthetic(n_clusters=300, size=4, n_solo=600, seed=0):
    """Scene quality drives global labels; frame quality drives within-stack picks."""
    rng = np.random.default_rng(seed)
    stack = np.repeat(np.arange(1, n_clusters + 1), size)
    stack = np.concatenate([stack, np.zeros(n_solo, dtype=int)])
    n = stack.size
    scene = np.where(stack > 0, rng.normal(0, 1, n_clusters + 1)[stack], rng.normal(0, 1, n))
    frame = rng.normal(0, 1, n)
    series = {
        "scene_model": 0.5 + 0.1 * scene + rng.normal(0, 0.01, n),
        "frame_model": 0.5 + 0.1 * frame + rng.normal(0, 0.01, n),
        "both_model": 0.5 + 0.1 * scene + 0.1 * frame + rng.normal(0, 0.01, n),
        "noise_model": rng.random(n),
    }
    grades = np.full(n, -1, dtype=np.int8)
    for c in range(1, n_clusters + 1):
        idx = np.flatnonzero(stack == c)
        order = idx[np.argsort(frame[idx])]
        grades[idx] = 1
        grades[order[-1]] = 2
        grades[order[0]] = 0
    global_label = np.clip(np.round(3 + 1.2 * scene), 1, 5)
    return series, stack, grades, global_label


def _matrix(series, stack, grades):
    n = stack.size
    image_rows = [(i + 1, None, None, None, int(stack[i]), 0) for i in range(n)]
    score_rows = [(i + 1, k, float(v[i]), False) for k, v in series.items() for i in range(n)]
    m = data.build_matrix(image_rows, score_rows, "fp")
    pick = {2: 1, 1: 0, 0: -1, -1: 0}
    m.pick_status[:] = [pick[int(g)] for g in grades]
    return m


def test_bh_adjust_matches_reference():
    p = np.array([0.01, 0.04, 0.03, 0.2, np.nan])
    adj = su.bh_adjust(p)
    assert np.allclose(adj[:4], [0.04, 0.0533333, 0.0533333, 0.2])
    assert np.isnan(adj[4])


def test_profile_flags_bounds_ties_and_saturation():
    x = np.array([0.0, 0.0, 0.5, 0.5, 1.0, 1.2, np.nan])
    p = su.profile(x, b=50)
    assert p["n"] == 6 and p["missing_pct"] == pytest.approx(100 / 7, abs=1e-3)
    assert p["above_bound"] == 1 and p["below_bound"] == 0
    assert p["floor_pct"] == pytest.approx(100 * 2 / 6)
    assert p["unique"] == 4 and p["tie_fraction"] == pytest.approx(1 / 3)
    assert set(p["percentiles"]) >= {"1", "50", "99.9"}
    assert len(p["ecdf"]["q"]) == su.ECDF_POINTS
    assert p["mean_ci"][0] <= p["mean"] <= p["mean_ci"][1]


def test_variance_decomposition_separates_scene_and_frame():
    series, stack, _, _ = _synthetic()
    scene = su.variance_decomposition(series["scene_model"], stack, b=50)
    frame = su.variance_decomposition(series["frame_model"], stack, b=50)
    assert scene["within_share_image_weighted"] < 0.05
    assert frame["within_share_image_weighted"] > 0.6
    assert scene["icc1"] > 0.9 and frame["icc1"] < 0.2
    lo, hi = frame["within_share_cluster_weighted_ci"]
    assert lo <= frame["within_share_cluster_weighted"] <= hi


def test_pooled_vs_within_detects_simpson_flip():
    rng = np.random.default_rng(1)
    stack = np.repeat(np.arange(1, 201), 5)
    scene = rng.normal(0, 1, 201)[stack]
    frame = rng.normal(0, 0.3, stack.size)
    a = scene + frame
    b = scene - frame  # positively related across scenes, negatively within a stack
    res = su.correlation_suite({"a": a, "b": b}, ["a", "b"], stack)
    assert res["pooled_spearman"]["r"][0][1] > 0.5
    assert res["within_spearman"]["r"][0][1] < -0.5
    assert res["pooled_vs_within"][0]["sign_flip"] is True
    assert res["within_pearson"]["p_bh"][0][1] is not None
    assert res["distance_correlation"]["r"][0][1] > 0


def test_build_pairs_weights_each_cluster_once():
    stack = np.array([1, 1, 1, 2, 2, 0])
    grades = np.array([2, 1, 0, 1, 1, 2], dtype=np.int8)
    pairs = su.build_pairs(stack, grades)
    assert pairs["a"].size == 4  # 3 pairs in stack 1, 1 in stack 2, none for standalone
    per_cluster = np.bincount(pairs["cluster"], weights=pairs["w"])
    assert per_cluster[0] == pytest.approx(1.0)
    assert per_cluster[1] == 0  # all-tied cluster has no decisive pairs


def test_culling_metrics_perfect_and_reversed():
    series, stack, grades, _ = _synthetic(n_clusters=120, n_solo=0)
    pairs = su.build_pairs(stack, grades)
    good = su.culling_metrics(series["frame_model"], pairs, stack, grades, b=50)
    bad = su.culling_metrics(-series["frame_model"], pairs, stack, grades, b=50)
    scene = su.culling_metrics(series["scene_model"], pairs, stack, grades, b=50)
    assert good["pairwise_accuracy_macro"] >= 0.9
    assert good["top1_agreement"] > 0.8 and good["ndcg_at_3"] > 0.8
    assert good["kendall_tau_b_mean"] > 0.8
    assert bad["pairwise_accuracy_macro"] <= 0.1
    assert 0.35 < scene["pairwise_accuracy_macro"] < 0.65
    lo, hi = good["pairwise_accuracy_macro_ci"]
    assert lo <= good["pairwise_accuracy_macro"] <= hi


def test_pairwise_logit_is_reversal_symmetric_and_learns_signal():
    series, stack, grades, _ = _synthetic(n_clusters=200, n_solo=0)
    pairs = su.build_pairs(stack, grades)
    res = su.pairwise_logit_study(series, ["frame_model", "scene_model", "noise_model"], pairs, folds=4)
    coef = {c["dimension"]: c for c in res["coefficients"]}
    assert res["cv"]["accuracy"] > 0.9
    assert coef["frame_model"]["beta_std"] > 1.0
    assert coef["frame_model"]["marginal_log_loss_gain"] > coef["noise_model"]["marginal_log_loss_gain"]
    z = np.array([0.3, -1.2])
    assert np.allclose(su._sigmoid(z) + su._sigmoid(-z), 1.0)


def test_global_metrics_downweight_bursts():
    series, stack, _, label = _synthetic()
    g = su.global_metrics(series["scene_model"], label, stack, b=50)
    f = su.global_metrics(series["frame_model"], label, stack, b=50)
    assert g["spearman_weighted"] > 0.8 and abs(f["spearman_weighted"]) < 0.2
    lo, hi = g["spearman_weighted_ci"]
    assert lo <= g["spearman_weighted"] <= hi


def test_suitability_map_roles():
    rows = su.suitability_map(
        ["g", "c", "x"],
        {"g": "model", "c": "model", "x": "composite"},
        {"g": {"spearman_weighted": 0.8, "spearman_weighted_ci": (0.7, 0.9)}, "c": {"spearman_weighted_ci": (0.0, 0.1)}},
        {"c": {"pairwise_accuracy_macro": 0.9, "pairwise_accuracy_macro_ci": (0.85, 0.95)}, "g": {"pairwise_accuracy_macro_ci": (0.45, 0.55)}},
        global_min=0.3,
        culling_min=0.6,
        global_independent=True,
        culling_independent=False,
    )
    by = {r["dimension"]: r for r in rows}
    assert by["g"]["role"] == "global" and by["c"]["role"] == "culling"
    assert by["c"]["provisional"] is True
    assert by["x"]["role"] == "unknown"
    assert any("derived" in c for c in by["x"]["caveats"])


def test_labels_assemble_provenance_and_leakage():
    series, stack, grades, label = _synthetic(n_clusters=40, n_solo=10)
    m = _matrix(series, stack, grades)
    ids = m.image_ids.tolist()
    manual = [(ids[i], {2: "pick", 1: "keep", 0: "reject"}[int(g)], "2026-01-01") for i, g in enumerate(grades) if g >= 0]
    rows = {
        "culling_manual": manual,
        "pick_status": [(ids[0], 1, "1.0"), (ids[5], -1, None)],
        "xmp": [(ids[i], int(label[i]), None, None) for i in range(len(ids))],
        "score_rating": [(ids[i], int(label[i])) for i in range(len(ids))],
    }
    b = labels.assemble(m, rows)
    assert b.culling_source == "culling_manual" and b.culling_independent
    assert b.audit["sources"]["pick_status_auto_policy"]["images"] >= 1
    assert b.global_independent is False  # XMP mirrors score-derived rating → leakage flagged
    assert any("written back" in n for n in b.audit["notes"])

    few = labels.assemble(m, {**rows, "culling_manual": manual[:8]})
    assert few.culling_source == "pick_status_unverified" and not few.culling_independent


def test_build_report_recovers_roles_on_synthetic_library():
    series, stack, grades, label = _synthetic(n_clusters=400, n_solo=800)
    m = _matrix(series, stack, grades)
    ids = m.image_ids.tolist()
    rows = {
        "culling_manual": [(ids[i], {2: "pick", 1: "keep", 0: "reject"}[int(g)], "t") for i, g in enumerate(grades) if g >= 0],
        "xmp": [(ids[i], int(label[i]), None, None) for i in range(len(ids))],
        "score_rating": [],
    }
    bundle = labels.assemble(m, rows, trust_xmp_ratings=True)
    rep = sr.build_report(m, bundle, bootstrap=60, min_test_clusters=30)
    roles = {r["dimension"]: r["role"] for r in rep["suitability"]["map"]}
    assert roles["scene_model"] == "global"
    assert roles["frame_model"] == "culling"
    assert roles["both_model"] == "both"
    assert roles["noise_model"] == "neither"
    assert rep["suitability"]["evaluation_set"] == "untouched test split"
    hold = rep["pairwise_model"]["holdout"]
    assert hold["test_calibrated"]["accuracy"] > 0.85
    assert rep["split"]["images"]["test"] > 0
    assert any(s["stratum"] == "stack_size" for s in rep["subgroups"])
    json.dumps(rep, allow_nan=False)  # API/JSON-safe (no numpy scalars, no NaN)
    man = sr.manifest(m, {"bootstrap": 60})
    assert man["read_only"] and len(man["query_hash"]) == 40


def test_split_is_deterministic():
    ids = np.arange(1, 1001)
    s1, s2 = sr.split_of(ids, 0.2, 0.2), sr.split_of(ids, 0.2, 0.2)
    assert (s1 == s2).all()
    assert 0.12 < (s1 == 2).mean() < 0.28


@pytest.fixture(scope="module")
def report_script():
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "analysis" / "model_suitability_report.py"
    spec = importlib.util.spec_from_file_location("model_suitability_report", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_report_script_writes_artifacts(tmp_path, report_script):
    series, stack, grades, label = _synthetic(n_clusters=150, n_solo=200)
    m = _matrix(series, stack, grades)
    ids = m.image_ids.tolist()
    rows = {
        "culling_manual": [(ids[i], {2: "pick", 1: "keep", 0: "reject"}[int(g)], "t") for i, g in enumerate(grades) if g >= 0],
        "xmp": [(ids[i], int(label[i]), None, None) for i in range(len(ids))],
    }
    bundle = labels.assemble(m, rows, trust_xmp_ratings=True)
    rep = sr.build_report(m, bundle, bootstrap=40, min_test_clusters=10)
    man = sr.manifest(m, {"bootstrap": 40})
    files = report_script.write_report(rep, man, [{"dimension": "frame_model", "versions": [{"version": "v1", "rows": 3}]}], tmp_path, {"csv", "json"})
    for rel in ("manifest.json", "profiles.csv", "variance_decomposition.csv", "correlation/within_spearman.csv",
                "culling_metrics_test.csv", "suitability_map.csv", "subgroups.csv", "REPORT.md"):
        assert rel in files and (tmp_path / rel).exists()
    md = (tmp_path / "REPORT.md").read_text()
    assert "Suitability map" in md and "frame_model" in md and "Label provenance" in md
