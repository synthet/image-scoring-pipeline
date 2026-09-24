"""Pure statistics for score-dimension analysis (no DB access).

Implements the workflow from the score-dimension modelling brief: univariate
descriptives, pairwise Pearson/Spearman correlation, VIF multicollinearity
diagnostics, OLS regression of an overall score on component scores, and
rule-based recommendations. Inputs are float arrays with NaN for missing.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import stats as sps

HISTOGRAM_BINS = 50
MODE_BINS = 100
RESIDUAL_HIST_BINS = 40
MIN_REGRESSION_ROWS = 30

HIGH_CORRELATION = 0.8
VIF_WARN = 5.0
VIF_HIGH = 10.0
SKEW_THRESHOLD = 1.0
ALPHA = 0.05


def finite_or_none(v: Any) -> float | None:
    """Convert numpy/python numbers to JSON-safe floats (non-finite -> None)."""
    if v is None:
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def _hist_range(x: np.ndarray) -> tuple[float, float]:
    lo, hi = float(x.min()), float(x.max())
    if lo >= 0.0 and hi <= 1.0:
        return 0.0, 1.0
    if hi <= lo:
        return lo - 0.5, hi + 0.5
    return lo, hi


def histogram(x: np.ndarray, bins: int, value_range: tuple[float, float] | None = None) -> dict[str, Any]:
    """Compact histogram ``{lo, hi, counts}`` with equal-width bins."""
    if x.size == 0:
        lo, hi = value_range or (0.0, 1.0)
        return {"lo": lo, "hi": hi, "counts": [0] * bins}
    lo, hi = value_range or _hist_range(x)
    counts, _ = np.histogram(x, bins=bins, range=(lo, hi))
    return {"lo": lo, "hi": hi, "counts": counts.astype(int).tolist()}


def describe(values: np.ndarray, total: int | None = None) -> dict[str, Any]:
    """Univariate summary: central tendency, dispersion, shape, box and histogram."""
    x = np.asarray(values, dtype=np.float64)
    x = x[np.isfinite(x)]
    n = int(x.size)
    out: dict[str, Any] = {
        "count": n,
        "coverage_pct": round(100.0 * n / total, 2) if total else None,
    }
    if n == 0:
        out["histogram"] = histogram(x, HISTOGRAM_BINS)
        return out

    q1, median, q3 = np.percentile(x, [25, 50, 75])
    iqr = q3 - q1
    mode_hist = histogram(x, MODE_BINS)
    peak = int(np.argmax(mode_hist["counts"]))
    width = (mode_hist["hi"] - mode_hist["lo"]) / MODE_BINS
    lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inside = x[(x >= lo_fence) & (x <= hi_fence)]

    out.update(
        {
            "mean": finite_or_none(x.mean()),
            "median": finite_or_none(median),
            "mode": finite_or_none(mode_hist["lo"] + (peak + 0.5) * width),
            "min": finite_or_none(x.min()),
            "max": finite_or_none(x.max()),
            "range": finite_or_none(x.max() - x.min()),
            "q1": finite_or_none(q1),
            "q3": finite_or_none(q3),
            "iqr": finite_or_none(iqr),
            "variance": finite_or_none(x.var(ddof=1)) if n > 1 else None,
            "std": finite_or_none(x.std(ddof=1)) if n > 1 else None,
            "skewness": finite_or_none(sps.skew(x)) if n > 2 and x.std() > 0 else None,
            "kurtosis": finite_or_none(sps.kurtosis(x)) if n > 3 and x.std() > 0 else None,
            "whisker_lo": finite_or_none(inside.min()) if inside.size else None,
            "whisker_hi": finite_or_none(inside.max()) if inside.size else None,
            "outliers": int(n - inside.size),
            "histogram": histogram(x, HISTOGRAM_BINS),
        }
    )
    return out


def correlations(series: dict[str, np.ndarray], keys: list[str]) -> dict[str, Any]:
    """Pairwise-complete Pearson and Spearman matrices with p-values and n."""
    k = len(keys)
    empty = [[None] * k for _ in range(k)]
    result = {
        "pearson": [row[:] for row in empty],
        "pearson_p": [row[:] for row in empty],
        "spearman": [row[:] for row in empty],
        "spearman_p": [row[:] for row in empty],
        "n": [[0] * k for _ in range(k)],
    }
    finite = {key: np.isfinite(series[key]) for key in keys}
    for i, a in enumerate(keys):
        result["n"][i][i] = int(finite[a].sum())
        if result["n"][i][i] > 2:
            for m in ("pearson", "spearman"):
                result[m][i][i] = 1.0
                result[f"{m}_p"][i][i] = 0.0
        for j in range(i + 1, k):
            b = keys[j]
            mask = finite[a] & finite[b]
            n = int(mask.sum())
            result["n"][i][j] = result["n"][j][i] = n
            if n < 3:
                continue
            xa, xb = series[a][mask], series[b][mask]
            if xa.std() == 0 or xb.std() == 0:
                continue
            pr = sps.pearsonr(xa, xb)
            sr = sps.spearmanr(xa, xb)
            for m, res in (("pearson", pr), ("spearman", sr)):
                r = finite_or_none(res.statistic)
                p = finite_or_none(res.pvalue)
                result[m][i][j] = result[m][j][i] = r
                result[f"{m}_p"][i][j] = result[f"{m}_p"][j][i] = p
    return result


def _r_squared(y: np.ndarray, X: np.ndarray) -> float:
    A = np.column_stack([np.ones(len(y)), X])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ beta
    sst = float(((y - y.mean()) ** 2).sum())
    if sst == 0:
        return 1.0
    return 1.0 - float(resid @ resid) / sst


def vif(X: np.ndarray) -> list[float]:
    """Variance inflation factor per column (``inf`` for perfect collinearity)."""
    k = X.shape[1]
    if k < 2:
        return [1.0] * k
    out: list[float] = []
    for j in range(k):
        r2 = _r_squared(X[:, j], np.delete(X, j, axis=1))
        out.append(math.inf if r2 >= 1.0 - 1e-10 else 1.0 / (1.0 - r2))
    return out


def _fit(y: np.ndarray, A: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    return beta


def cross_validated_r2(y: np.ndarray, X: np.ndarray, folds: int = 5, seed: int = 0) -> float | None:
    """Pooled out-of-fold R² from a seeded k-fold split."""
    n = len(y)
    if n < folds * 2:
        return None
    rng = np.random.default_rng(seed)
    A = np.column_stack([np.ones(n), X])
    pred = np.empty(n)
    for idx in np.array_split(rng.permutation(n), folds):
        train = np.ones(n, dtype=bool)
        train[idx] = False
        pred[idx] = A[idx] @ _fit(y[train], A[train])
    sst = float(((y - y.mean()) ** 2).sum())
    if sst == 0:
        return None
    return 1.0 - float(((y - pred) ** 2).sum()) / sst


def ols(
    y: np.ndarray,
    X: np.ndarray,
    names: list[str],
    *,
    residual_sample: int = 20_000,
    seed: int = 0,
) -> dict[str, Any]:
    """Multiple linear regression by OLS with inference and fit metrics.

    ``y`` and ``X`` must already be complete cases (no NaN).
    """
    n, k = X.shape
    dof = n - k - 1
    if dof < 1:
        raise ValueError(f"Need more rows than predictors (n={n}, k={k})")
    A = np.column_stack([np.ones(n), X])
    beta = _fit(y, A)
    fitted = A @ beta
    resid = y - fitted
    sse = float(resid @ resid)
    sst = float(((y - y.mean()) ** 2).sum())
    sigma2 = sse / dof
    cov = sigma2 * np.linalg.pinv(A.T @ A)
    se = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    with np.errstate(divide="ignore", invalid="ignore"):
        t = beta / se
    p = 2.0 * sps.t.sf(np.abs(t), dof)
    t_crit = float(sps.t.ppf(1 - ALPHA / 2, dof))
    rank = int(np.linalg.matrix_rank(A))

    r2 = 1.0 - sse / sst if sst > 0 else None
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / dof if r2 is not None else None
    if sst > 0 and sse > 0 and k > 0:
        f_stat = ((sst - sse) / k) / (sse / dof)
        f_p = float(sps.f.sf(f_stat, k, dof))
    elif sst > 0 and k > 0:
        f_stat, f_p = math.inf, 0.0
    else:
        f_stat, f_p = None, None

    y_std = float(y.std())
    x_std = X.std(axis=0)
    vifs = vif(X)
    coefficients = []
    for j, name in enumerate(names):
        b = beta[j + 1]
        coefficients.append(
            {
                "name": name,
                "beta": finite_or_none(b),
                "std_beta": finite_or_none(b * x_std[j] / y_std) if y_std > 0 else None,
                "se": finite_or_none(se[j + 1]),
                "t": finite_or_none(t[j + 1]),
                "p": finite_or_none(p[j + 1]),
                "ci_lo": finite_or_none(b - t_crit * se[j + 1]),
                "ci_hi": finite_or_none(b + t_crit * se[j + 1]),
                "vif": finite_or_none(vifs[j]),
                "vif_infinite": math.isinf(vifs[j]),
            }
        )

    rng = np.random.default_rng(seed)
    if n > residual_sample:
        sample_idx = np.sort(rng.choice(n, residual_sample, replace=False))
    else:
        sample_idx = np.arange(n)

    return {
        "n": n,
        "k": k,
        "rank_deficient": rank < k + 1,
        "intercept": {
            "beta": finite_or_none(beta[0]),
            "se": finite_or_none(se[0]),
            "t": finite_or_none(t[0]),
            "p": finite_or_none(p[0]),
            "ci_lo": finite_or_none(beta[0] - t_crit * se[0]),
            "ci_hi": finite_or_none(beta[0] + t_crit * se[0]),
        },
        "coefficients": coefficients,
        "r2": finite_or_none(r2),
        "adj_r2": finite_or_none(adj_r2),
        "cv_r2": finite_or_none(cross_validated_r2(y, X, seed=seed)),
        "rmse": finite_or_none(math.sqrt(sse / n)),
        "mae": finite_or_none(np.abs(resid).mean()),
        "f_stat": finite_or_none(f_stat),
        "f_p": finite_or_none(f_p),
        "dof": dof,
        "residuals": {
            "fitted": np.round(fitted[sample_idx], 4).tolist(),
            "residual": np.round(resid[sample_idx], 4).tolist(),
            "sampled": int(sample_idx.size),
            "histogram": histogram(resid, RESIDUAL_HIST_BINS, _symmetric_range(resid)),
        },
    }


def _symmetric_range(x: np.ndarray) -> tuple[float, float]:
    m = float(np.abs(x).max()) if x.size else 0.0
    m = m if m > 0 else 1e-6
    return -m, m


def recommendations(
    names: list[str],
    X: np.ndarray,
    y: np.ndarray,
    target: str,
    fit: dict[str, Any],
) -> list[dict[str, str]]:
    """Rule-based feature-adjustment suggestions for a fitted model."""
    recs: list[dict[str, str]] = []
    k = len(names)

    if k >= 2:
        with np.errstate(invalid="ignore", divide="ignore"):
            corr = np.corrcoef(X, rowvar=False)
        for i in range(k):
            for j in range(i + 1, k):
                r = corr[i, j]
                if math.isfinite(r) and abs(r) >= HIGH_CORRELATION:
                    recs.append(
                        {
                            "severity": "warn",
                            "message": (
                                f"{names[i]} and {names[j]} are highly correlated (r={r:.2f}); "
                                "they likely measure the same thing — consider dropping one or averaging them."
                            ),
                        }
                    )

    high_vif = 0
    for c in fit["coefficients"]:
        if c["vif_infinite"]:
            high_vif += 1
            recs.append(
                {
                    "severity": "high",
                    "message": f"{c['name']} is perfectly collinear with other predictors (VIF=∞); remove it.",
                }
            )
        elif c["vif"] is not None and c["vif"] > VIF_HIGH:
            high_vif += 1
            recs.append(
                {
                    "severity": "high",
                    "message": f"{c['name']} has VIF={c['vif']:.1f} (>10): severe multicollinearity, coefficient unstable.",
                }
            )
        elif c["vif"] is not None and c["vif"] > VIF_WARN:
            high_vif += 1
            recs.append(
                {
                    "severity": "warn",
                    "message": f"{c['name']} has VIF={c['vif']:.1f} (>5): notable multicollinearity.",
                }
            )
        if c["p"] is not None and c["p"] > ALPHA:
            recs.append(
                {
                    "severity": "info",
                    "message": (
                        f"{c['name']} is not significant (p={c['p']:.3f}); it adds little beyond the other "
                        "predictors and could be dropped."
                    ),
                }
            )

    if high_vif >= 2:
        recs.append(
            {
                "severity": "info",
                "message": (
                    "Several predictors are collinear — consider Ridge/Lasso regularisation or PCA "
                    "to combine them into orthogonal components."
                ),
            }
        )

    for label, col in [(target, y)] + [(names[j], X[:, j]) for j in range(k)]:
        if col.size > 2 and col.std() > 0:
            s = float(sps.skew(col))
            if abs(s) > SKEW_THRESHOLD:
                recs.append(
                    {
                        "severity": "info",
                        "message": (
                            f"{label} is strongly skewed (skewness={s:.2f}); a log or rank transform may "
                            "stabilise variance."
                        ),
                    }
                )

    adj, cv = fit.get("adj_r2"), fit.get("cv_r2")
    if adj is not None and cv is not None and adj - cv > 0.05:
        recs.append(
            {
                "severity": "warn",
                "message": f"Cross-validated R² ({cv:.3f}) is well below adjusted R² ({adj:.3f}): possible overfitting.",
            }
        )
    if fit.get("r2") is not None and fit["r2"] >= 0.99:
        recs.append(
            {
                "severity": "info",
                "message": (
                    f"{target} is almost exactly a linear function of these predictors (R²≥0.99); the "
                    "coefficients effectively recover its fusion weights."
                ),
            }
        )
    if not any(r["severity"] in ("high", "warn") for r in recs):
        recs.append(
            {
                "severity": "ok",
                "message": "No severe multicollinearity or overfitting detected for this predictor set.",
            }
        )
    return recs
