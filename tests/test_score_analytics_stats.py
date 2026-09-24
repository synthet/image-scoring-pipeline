"""Unit tests for modules.score_analytics.stats (pure numpy/scipy, no DB)."""

import math

import numpy as np
import pytest
from scipy import stats as sps

from modules.score_analytics import stats


@pytest.fixture
def rng():
    return np.random.default_rng(42)


def test_describe_matches_numpy_and_scipy(rng):
    x = rng.beta(2, 5, size=5000)
    x_with_nan = np.concatenate([x, [np.nan] * 100])
    d = stats.describe(x_with_nan, total=5100)

    assert d["count"] == 5000
    assert d["coverage_pct"] == pytest.approx(98.04, abs=0.01)
    assert d["mean"] == pytest.approx(x.mean())
    assert d["median"] == pytest.approx(np.median(x))
    assert d["std"] == pytest.approx(x.std(ddof=1))
    assert d["iqr"] == pytest.approx(np.percentile(x, 75) - np.percentile(x, 25))
    assert d["skewness"] == pytest.approx(sps.skew(x))
    assert d["kurtosis"] == pytest.approx(sps.kurtosis(x))
    assert d["skewness"] > 0  # beta(2,5) is right-skewed
    assert sum(d["histogram"]["counts"]) == 5000
    assert len(d["histogram"]["counts"]) == stats.HISTOGRAM_BINS
    assert (d["histogram"]["lo"], d["histogram"]["hi"]) == (0.0, 1.0)
    # Mode of beta(2,5) is (a-1)/(a+b-2) = 0.2.
    assert d["mode"] == pytest.approx(0.2, abs=0.1)
    assert d["whisker_lo"] >= d["min"] and d["whisker_hi"] <= d["max"]


def test_describe_empty_and_constant():
    empty = stats.describe(np.array([np.nan, np.nan]), total=2)
    assert empty["count"] == 0
    assert "mean" not in empty

    const = stats.describe(np.full(10, 0.5))
    assert const["std"] == 0
    assert const["skewness"] is None and const["kurtosis"] is None


def test_correlations_pairwise_complete_and_spearman_monotonic(rng):
    a = rng.random(1000)
    b = a**3  # monotonic, non-linear
    c = rng.random(1000)
    b[:100] = np.nan
    res = stats.correlations({"a": a, "b": b, "c": c}, ["a", "b", "c"])

    assert res["n"][0][1] == 900
    assert res["n"][0][0] == 1000
    assert res["spearman"][0][1] == pytest.approx(1.0)
    assert res["pearson"][0][1] < 0.95
    assert abs(res["pearson"][0][2]) < 0.1
    assert res["pearson"][1][0] == res["pearson"][0][1]
    assert res["pearson_p"][0][1] < 1e-10


def test_ols_recovers_coefficients(rng):
    n = 2000
    a, b = rng.random(n), rng.random(n)
    y = 0.1 + 2 * a + 3 * b + rng.normal(0, 0.01, n)
    fit = stats.ols(y, np.column_stack([a, b]), ["a", "b"])

    coef = {c["name"]: c for c in fit["coefficients"]}
    assert coef["a"]["beta"] == pytest.approx(2, abs=0.01)
    assert coef["b"]["beta"] == pytest.approx(3, abs=0.01)
    assert fit["intercept"]["beta"] == pytest.approx(0.1, abs=0.01)
    assert coef["a"]["ci_lo"] < 2 < coef["a"]["ci_hi"]
    assert coef["a"]["p"] < 1e-10
    assert fit["r2"] > 0.999
    assert fit["adj_r2"] <= fit["r2"]
    assert fit["cv_r2"] == pytest.approx(fit["r2"], abs=1e-3)
    assert fit["f_p"] < 1e-10
    assert fit["rmse"] == pytest.approx(0.01, rel=0.1)
    assert coef["a"]["vif"] == pytest.approx(1.0, abs=0.05)
    assert fit["residuals"]["sampled"] == n
    assert sum(fit["residuals"]["histogram"]["counts"]) == n


def test_ols_residual_sampling_caps_points(rng):
    n = 500
    X = rng.random((n, 1))
    y = X[:, 0] + rng.normal(0, 0.1, n)
    fit = stats.ols(y, X, ["x"], residual_sample=100)
    assert len(fit["residuals"]["fitted"]) == 100


def test_vif_detects_collinearity(rng):
    a = rng.random(500)
    X = np.column_stack([a, a * 2 + 1, rng.random(500)])
    v = stats.vif(X)
    assert math.isinf(v[0]) and math.isinf(v[1])
    assert v[2] < 1.1


def test_recommendations_flag_redundancy_and_nonsignificance(rng):
    n = 1000
    a = rng.random(n)
    a_dup = a + rng.normal(0, 0.001, n)
    noise = rng.random(n)
    y = a + rng.normal(0, 0.05, n)
    X = np.column_stack([a, a_dup, noise])
    names = ["a", "a_dup", "noise"]
    fit = stats.ols(y, X, names)
    recs = stats.recommendations(names, X, y, "y", fit)
    text = " ".join(r["message"] for r in recs)

    assert "highly correlated" in text
    assert any(r["severity"] == "high" and "VIF" in r["message"] for r in recs)
    assert "noise is not significant" in text
    assert "Ridge/Lasso" in text
    assert not any(r["severity"] == "ok" for r in recs)


def test_recommendations_skew_and_ok(rng):
    n = 1000
    a = rng.random(n)
    b = rng.random(n)
    y = a + b + rng.normal(0, 0.3, n)
    X = np.column_stack([a, b])
    fit = stats.ols(y, X, ["a", "b"])
    recs = stats.recommendations(["a", "b"], X, y, "y", fit)
    assert [r["severity"] for r in recs] == ["ok"]

    skewed = rng.exponential(size=n)
    Xs = np.column_stack([skewed, b])
    fit_s = stats.ols(y, Xs, ["skewed", "b"])
    recs_s = stats.recommendations(["skewed", "b"], Xs, y, "y", fit_s)
    assert any("skewed is strongly skewed" in r["message"] for r in recs_s)


def test_ols_requires_more_rows_than_predictors():
    with pytest.raises(ValueError):
        stats.ols(np.array([1.0, 2.0]), np.array([[1.0, 2.0], [3.0, 4.0]]), ["a", "b"])
