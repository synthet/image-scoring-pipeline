"""Global (Nₐ) vs intra-cluster (Nᵦ) model suitability — pure numpy/scipy, no DB.

Implements the statistical core of the "global vs cluster model suitability"
research canvas:

* extended per-dimension profiles (bounds, ties, saturation, heaping, entropy,
  bimodality, bootstrap CIs, ECDF / normal-QQ quantiles)
* law-of-total-variance decomposition (image- and cluster-weighted, ICC(1))
* pooled vs within-cluster-centered correlation, Kendall τ-b, partial and
  distance correlation, Benjamini–Hochberg adjusted p-values, PCA
* within-cluster pairwise culling metrics against graded labels
  (pick=2 > neutral=1 > reject=0): pairwise accuracy, top-1, NDCG@k, τ-b,
  all with (Poisson) cluster-bootstrap CIs
* intercept-free, cluster-weighted pairwise logistic model
  P(a ≻ b) = σ(Σ βⱼ Δⱼ) with grouped CV by cluster, ablation and ECE
* global agreement Gⱼ with an independent label (burst-downweighted Spearman)
* the suitability map Uⱼ = (Gⱼ, Cⱼ) with prespecified thresholds

Labels are passed in; whether they are independent of the scores is decided by
``labels.py`` (provenance audit) and reported, never assumed here.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import stats as sps

from modules.score_analytics.stacks import group_average_ranks
from modules.score_analytics.stats import finite_or_none

PERCENTILES = (1, 5, 10, 25, 50, 75, 90, 95, 99, 99.5, 99.9)
NEAR_BOUND = 0.01
ENTROPY_BINS = 50
ECDF_POINTS = 101
DEFAULT_BOOTSTRAP = 200
TIE_EPS = 1e-9
PAIR_CAP_PER_CLUSTER = 2000
KENDALL_SAMPLE = 20_000
DCOR_SAMPLE = 1_000


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _f(v: Any) -> float | None:
    return finite_or_none(v) if v is not None else None


def average_ranks(x: np.ndarray) -> np.ndarray:
    return sps.rankdata(x, method="average")


def group_index(groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Map arbitrary group ids to 0..G-1; returns (codes, sizes)."""
    _, codes, sizes = np.unique(groups, return_inverse=True, return_counts=True)
    return codes, sizes


def singleton_groups(stack_ids: np.ndarray) -> np.ndarray:
    """Cluster id per image with standalone images as their own negative-id cluster."""
    out = stack_ids.astype(np.int64).copy()
    solo = out <= 0
    out[solo] = -(np.arange(solo.sum()) + 1)
    return out


def bh_adjust(p: np.ndarray) -> np.ndarray:
    """Benjamini–Hochberg FDR-adjusted p-values (NaN-preserving)."""
    p = np.asarray(p, dtype=float)
    out = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if m == 0:
        return out
    pv = p[ok]
    order = np.argsort(pv)
    ranked = pv[order] * m / np.arange(1, m + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    adj = np.empty(m)
    adj[order] = np.clip(ranked, 0, 1)
    out[ok] = adj
    return out


def _weighted_pearson(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted Pearson for weight matrix ``w`` (B × n) against fixed x, y → B values."""
    sw = w.sum(axis=1)
    mx = (w @ x) / sw
    my = (w @ y) / sw
    cov = (w @ (x * y)) / sw - mx * my
    vx = (w @ (x * x)) / sw - mx * mx
    vy = (w @ (y * y)) / sw - my * my
    with np.errstate(invalid="ignore", divide="ignore"):
        return cov / np.sqrt(vx * vy)


def _boot_mean(W: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Weighted means per bootstrap draw; empty draws (all-zero Poisson weights) → NaN, dropped by ``_ci``."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return (W @ v) / W.sum(axis=1)


def _ci(samples: np.ndarray, level: float = 0.95) -> tuple[float | None, float | None]:
    s = samples[np.isfinite(samples)]
    if s.size < 10:
        return None, None
    a = (1 - level) / 2
    return float(np.quantile(s, a)), float(np.quantile(s, 1 - a))


def cluster_bootstrap_weights(codes: np.ndarray, n_groups: int, b: int, seed: int) -> np.ndarray:
    """B × G Poisson(1) cluster-bootstrap weights (whole clusters resampled; ~multinomial for large G)."""
    rng = np.random.default_rng(seed)
    return rng.poisson(1.0, size=(b, n_groups)).astype(np.float64)


# ---------------------------------------------------------------------------
# 5. descriptive & distributional audit
# ---------------------------------------------------------------------------


def profile(values: np.ndarray, *, total: int | None = None, bounds=(0.0, 1.0), b: int = DEFAULT_BOOTSTRAP, seed: int = 0) -> dict[str, Any]:
    """Extended descriptive profile of one score dimension."""
    raw = np.asarray(values, dtype=np.float64)
    total = total if total is not None else raw.size
    finite = raw[np.isfinite(raw)]
    n = int(finite.size)
    out: dict[str, Any] = {
        "n": n,
        "missing_pct": round(100.0 * (total - n) / total, 3) if total else None,
        "finite_pct": round(100.0 * n / total, 3) if total else None,
    }
    if n == 0:
        return out
    lo_b, hi_b = bounds
    q = np.percentile(finite, PERCENTILES)
    median = float(np.median(finite))
    uniq = np.unique(finite)
    std = float(finite.std(ddof=1)) if n > 1 else 0.0
    skew = float(sps.skew(finite)) if n > 2 and std > 0 else None
    kurt = float(sps.kurtosis(finite)) if n > 3 and std > 0 else None
    bimod = None
    if skew is not None and kurt is not None and n > 3:
        bimod = (skew**2 + 1) / (kurt + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))
    counts, _ = np.histogram(finite, bins=ENTROPY_BINS, range=(min(lo_b, finite.min()), max(hi_b, finite.max())))
    pk = counts[counts > 0] / n
    entropy = float(-(pk * np.log2(pk)).sum() / math.log2(ENTROPY_BINS))
    # Heaping: share of values lying on the 2-decimal grid beyond what 3-decimal data implies (~10%).
    on_grid = float(np.mean(np.isclose(np.round(finite, 2), finite, atol=1e-9)))

    rng = np.random.default_rng(seed)
    sample = finite if n <= 20_000 else rng.choice(finite, 20_000, replace=False)
    idx = rng.integers(0, sample.size, size=(b, sample.size))
    boots = sample[idx]
    mean_ci = _ci(boots.mean(axis=1))
    median_ci = _ci(np.median(boots, axis=1))

    grid = np.linspace(0, 1, ECDF_POINTS)
    sample_q = np.quantile(finite, grid)
    normal_q = sps.norm.ppf(np.clip(grid, 1e-3, 1 - 1e-3), loc=finite.mean(), scale=std or 1.0)

    out.update(
        {
            "min": float(finite.min()),
            "max": float(finite.max()),
            "below_bound": int((finite < lo_b).sum()),
            "above_bound": int((finite > hi_b).sum()),
            "mean": float(finite.mean()),
            "mean_ci": mean_ci,
            "median": median,
            "median_ci": median_ci,
            "variance": float(finite.var(ddof=1)) if n > 1 else None,
            "std": std,
            "mad": float(np.median(np.abs(finite - median))),
            "iqr": float(q[5] - q[3]),
            "percentiles": {str(p): float(v) for p, v in zip(PERCENTILES, q)},
            "skewness": _f(skew),
            "excess_kurtosis": _f(kurt),
            "bimodality_coefficient": _f(bimod),
            "bimodal_hint": bool(bimod is not None and bimod > 5 / 9),
            "unique": int(uniq.size),
            "tie_fraction": float(1 - uniq.size / n),
            "floor_pct": float(100 * np.mean(finite <= lo_b)),
            "ceiling_pct": float(100 * np.mean(finite >= hi_b)),
            "near_bound_pct": float(100 * np.mean((finite < lo_b + NEAR_BOUND) | (finite > hi_b - NEAR_BOUND))),
            "two_decimal_grid_pct": float(100 * on_grid),
            "entropy_norm": entropy,
            "ecdf": {"p": grid.round(3).tolist(), "q": sample_q.round(5).tolist()},
            "qq_normal": {"theoretical": normal_q.round(5).tolist(), "sample": sample_q.round(5).tolist()},
        }
    )
    return out


def co_missingness(series: dict[str, np.ndarray], keys: list[str]) -> list[list[float]]:
    """P(j missing | i missing) matrix (row i conditions)."""
    miss = np.column_stack([~np.isfinite(series[k]) for k in keys]).astype(np.float64)
    both = miss.T @ miss
    base = np.diag(both)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = both / base[:, None]
    return [[_f(v) for v in row] for row in m]


# ---------------------------------------------------------------------------
# 4. variance decomposition
# ---------------------------------------------------------------------------


def variance_decomposition(
    values: np.ndarray, clusters: np.ndarray, *, b: int = DEFAULT_BOOTSTRAP, seed: int = 0
) -> dict[str, Any]:
    """Var(s) = Var(E[s|C]) + E[Var(s|C)] over clusters of size ≥ 2.

    ``image`` weighting counts every image once; ``cluster`` weighting gives each
    cluster equal weight (bursts cannot dominate). ICC(1) from one-way ANOVA.
    """
    ok = np.isfinite(values) & (clusters > 0)
    x, g = values[ok], clusters[ok]
    if x.size == 0:
        return {"clusters": 0}
    codes, sizes = group_index(g)
    keep = sizes[codes] >= 2
    x, codes = x[keep], codes[keep]
    if x.size == 0:
        return {"clusters": 0}
    codes, sizes = group_index(codes)
    k = sizes.size
    sums = np.bincount(codes, weights=x)
    means = sums / sizes
    dev2 = np.bincount(codes, weights=(x - means[codes]) ** 2)
    within_var_c = dev2 / sizes

    def shares(w_img: np.ndarray, w_clu: np.ndarray) -> tuple[float, float]:
        # image-weighted
        grand = (w_img @ x) / w_img.sum()
        tot = (w_img @ (x - grand) ** 2) / w_img.sum()
        within_img = (w_img @ (x - means[codes]) ** 2) / w_img.sum()
        s_img = within_img / tot if tot > 0 else np.nan
        # cluster-weighted
        cm = (w_clu @ means) / w_clu.sum()
        between_c = (w_clu @ (means - cm) ** 2) / w_clu.sum()
        within_c = (w_clu @ within_var_c) / w_clu.sum()
        s_clu = within_c / (within_c + between_c) if (within_c + between_c) > 0 else np.nan
        return s_img, s_clu

    s_img, s_clu = shares(np.ones(x.size), np.ones(k))
    n = x.size
    msb = (sizes * (means - x.mean()) ** 2).sum() / max(k - 1, 1)
    msw = dev2.sum() / max(n - k, 1)
    n0 = (n - (sizes**2).sum() / n) / max(k - 1, 1)
    icc = (msb - msw) / (msb + (n0 - 1) * msw) if (msb + (n0 - 1) * msw) > 0 else np.nan

    W = cluster_bootstrap_weights(np.arange(k), k, b, seed)
    boot_img = np.empty(b)
    boot_clu = np.empty(b)
    for i in range(b):
        s1, s2 = shares(W[i][codes], W[i])
        boot_img[i], boot_clu[i] = s1, s2
    tot = x.var()
    return {
        "clusters": int(k),
        "images": int(n),
        "total_var": _f(tot),
        "between_var": _f(tot * (1 - s_img)),
        "within_var": _f(tot * s_img),
        "within_share_image_weighted": _f(s_img),
        "within_share_image_weighted_ci": _ci(boot_img),
        "within_share_cluster_weighted": _f(s_clu),
        "within_share_cluster_weighted_ci": _ci(boot_clu),
        "icc1": _f(icc),
        "median_within_sd": _f(np.median(np.sqrt(within_var_c * sizes / np.maximum(sizes - 1, 1)))),
        "median_within_range": _f(np.median(_group_range(x, codes, k))),
    }


def _group_range(x: np.ndarray, codes: np.ndarray, k: int) -> np.ndarray:
    mx = np.full(k, -np.inf)
    mn = np.full(k, np.inf)
    np.maximum.at(mx, codes, x)
    np.minimum.at(mn, codes, x)
    return mx - mn


# ---------------------------------------------------------------------------
# 6. correlation structure: pooled vs within-cluster
# ---------------------------------------------------------------------------


def within_center(values: np.ndarray, clusters: np.ndarray) -> np.ndarray:
    """Subtract cluster means (clusters of size ≥ 2 only; others → NaN)."""
    out = np.full(values.shape, np.nan)
    ok = np.isfinite(values) & (clusters > 0)
    if not ok.any():
        return out
    codes, sizes = group_index(clusters[ok])
    means = np.bincount(codes, weights=values[ok]) / sizes
    centered = values[ok] - means[codes]
    centered[sizes[codes] < 2] = np.nan
    out[ok] = centered
    return out


def within_rank_center(values: np.ndarray, clusters: np.ndarray) -> np.ndarray:
    """Within-cluster normalized ranks centered at 0 (for within-cluster Spearman)."""
    out = np.full(values.shape, np.nan)
    ok = np.isfinite(values) & (clusters > 0)
    if not ok.any():
        return out
    codes, sizes = group_index(clusters[ok])
    r = group_average_ranks(values[ok], codes)
    size = sizes[codes].astype(np.float64)
    centered = (r - (size - 1) / 2) / size
    centered[size < 2] = np.nan
    out[ok] = centered
    return out


def _pairwise_matrix(cols: list[np.ndarray], fn) -> tuple[list, list, list]:
    k = len(cols)
    r = [[None] * k for _ in range(k)]
    p = [[None] * k for _ in range(k)]
    n = [[0] * k for _ in range(k)]
    for i in range(k):
        for j in range(i, k):
            m = np.isfinite(cols[i]) & np.isfinite(cols[j])
            cnt = int(m.sum())
            n[i][j] = n[j][i] = cnt
            if cnt < 3 or cols[i][m].std() == 0 or cols[j][m].std() == 0:
                continue
            if i == j:
                r[i][i], p[i][i] = 1.0, 0.0
                continue
            rv, pv = fn(cols[i][m], cols[j][m])
            r[i][j] = r[j][i] = _f(rv)
            p[i][j] = p[j][i] = _f(pv)
    return r, p, n


def _bh_matrix(p: list[list[float | None]]) -> list[list[float | None]]:
    k = len(p)
    iu = np.triu_indices(k, 1)
    flat = np.array([p[i][j] if p[i][j] is not None else np.nan for i, j in zip(*iu)])
    adj = bh_adjust(flat)
    out = [[0.0 if i == j else None for j in range(k)] for i in range(k)]
    for v, i, j in zip(adj, *iu):
        out[i][j] = out[j][i] = _f(v)
    return out


def partial_correlation(cols: list[np.ndarray]) -> tuple[list, int]:
    """Partial correlations (each pair controlling for all others) on complete rows."""
    X = np.column_stack(cols)
    X = X[np.isfinite(X).all(axis=1)]
    k = X.shape[1]
    out: list[list[float | None]] = [[None] * k for _ in range(k)]
    if X.shape[0] <= k + 2:
        return out, int(X.shape[0])
    live = np.flatnonzero(X.std(axis=0) > 0)  # constant columns have no partial correlation
    if live.size < 2:
        return out, int(X.shape[0])
    try:
        P = np.linalg.pinv(np.corrcoef(X[:, live], rowvar=False))
    except np.linalg.LinAlgError:
        return out, int(X.shape[0])
    d = np.sqrt(np.abs(np.diag(P)))
    with np.errstate(invalid="ignore", divide="ignore"):
        pc = -P / np.outer(d, d)
    np.fill_diagonal(pc, 1.0)
    for a, i in enumerate(live):
        for b, j in enumerate(live):
            out[i][j] = _f(pc[a, b])
    return out, int(X.shape[0])


def distance_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """Székely distance correlation (captures non-linear dependence)."""
    a = np.abs(x[:, None] - x[None, :])
    b = np.abs(y[:, None] - y[None, :])
    A = a - a.mean(axis=0) - a.mean(axis=1)[:, None] + a.mean()
    B = b - b.mean(axis=0) - b.mean(axis=1)[:, None] + b.mean()
    dcov = (A * B).mean()
    dvx, dvy = (A * A).mean(), (B * B).mean()
    return float(np.sqrt(max(dcov, 0) / np.sqrt(dvx * dvy))) if dvx > 0 and dvy > 0 else float("nan")


def correlation_suite(series: dict[str, np.ndarray], keys: list[str], clusters: np.ndarray, *, seed: int = 0) -> dict[str, Any]:
    cols = [series[k] for k in keys]
    rng = np.random.default_rng(seed)
    out: dict[str, Any] = {"keys": keys}

    r, p, n = _pairwise_matrix(cols, lambda a, b: tuple(sps.pearsonr(a, b)))
    out["pooled_pearson"] = {"r": r, "p": p, "p_bh": _bh_matrix(p), "n": n}
    r, p, n = _pairwise_matrix(cols, lambda a, b: tuple(sps.spearmanr(a, b)))
    out["pooled_spearman"] = {"r": r, "p": p, "p_bh": _bh_matrix(p), "n": n}

    def kendall(a, b):
        if a.size > KENDALL_SAMPLE:
            idx = rng.choice(a.size, KENDALL_SAMPLE, replace=False)
            a, b = a[idx], b[idx]
        res = sps.kendalltau(a, b, variant="b")
        return res.statistic, res.pvalue

    r, p, n = _pairwise_matrix(cols, kendall)
    out["pooled_kendall_tau_b"] = {"r": r, "p": p, "p_bh": _bh_matrix(p), "n": n, "sample_cap": KENDALL_SAMPLE}

    centered = [within_center(c, clusters) for c in cols]
    r, p, n = _pairwise_matrix(centered, lambda a, b: tuple(sps.pearsonr(a, b)))
    out["within_pearson"] = {"r": r, "p": p, "p_bh": _bh_matrix(p), "n": n}
    ranked = [within_rank_center(c, clusters) for c in cols]
    r, p, n = _pairwise_matrix(ranked, lambda a, b: tuple(sps.pearsonr(a, b)))
    out["within_spearman"] = {"r": r, "p": p, "p_bh": _bh_matrix(p), "n": n}

    pc, n_complete = partial_correlation(cols)
    out["partial_pearson"] = {"r": pc, "n_complete": n_complete}

    k = len(keys)
    dc = [[None] * k for _ in range(k)]
    for i in range(k):
        for j in range(i, k):
            m = np.isfinite(cols[i]) & np.isfinite(cols[j])
            idx = np.flatnonzero(m)
            if idx.size < 10:
                continue
            if idx.size > DCOR_SAMPLE:
                idx = rng.choice(idx, DCOR_SAMPLE, replace=False)
            dc[i][j] = dc[j][i] = 1.0 if i == j else _f(distance_correlation(cols[i][idx], cols[j][idx]))
    out["distance_correlation"] = {"r": dc, "sample_cap": DCOR_SAMPLE}

    # Simpson-style divergence: pooled vs within-cluster sign/magnitude differences.
    div = []
    for i in range(k):
        for j in range(i + 1, k):
            a, w = out["pooled_spearman"]["r"][i][j], out["within_spearman"]["r"][i][j]
            if a is None or w is None:
                continue
            div.append({"a": keys[i], "b": keys[j], "pooled": a, "within": w, "delta": w - a, "sign_flip": (a > 0) != (w > 0)})
    out["pooled_vs_within"] = sorted(div, key=lambda d: -abs(d["delta"]))
    return out


def pca(series: dict[str, np.ndarray], keys: list[str]) -> dict[str, Any]:
    X = np.column_stack([series[k] for k in keys])
    X = X[np.isfinite(X).all(axis=1)]
    if X.shape[0] < len(keys) + 2:
        return {"n": int(X.shape[0])}
    Z = (X - X.mean(axis=0)) / np.where(X.std(axis=0) > 0, X.std(axis=0), 1)
    try:
        evals, evecs = np.linalg.eigh(np.cov(Z, rowvar=False))
    except np.linalg.LinAlgError:
        return {"n": int(X.shape[0]), "error": "eigendecomposition did not converge"}
    order = np.argsort(evals)[::-1]
    evals, evecs = evals[order], evecs[:, order]
    return {
        "n": int(X.shape[0]),
        "eigenvalues": [float(v) for v in evals],
        "explained": [float(v) for v in evals / evals.sum()],
        "loadings": {keys[i]: [float(v) for v in evecs[i, : min(4, len(keys))]] for i in range(len(keys))},
    }


# ---------------------------------------------------------------------------
# 7. pairwise culling formulation
# ---------------------------------------------------------------------------


def build_pairs(clusters: np.ndarray, grades: np.ndarray, *, cap: int = PAIR_CAP_PER_CLUSTER, seed: int = 0) -> dict[str, np.ndarray]:
    """All unordered within-cluster pairs among labelled images (grade ≥ 0).

    ``grades``: 2 pick, 1 neutral/keep, 0 reject, -1 unlabelled (excluded).
    Pairs per cluster are subsampled to ``cap``; ``w`` gives each cluster total
    weight 1 over its decisive pairs so large bursts cannot dominate.
    """
    rng = np.random.default_rng(seed)
    ok = np.flatnonzero((clusters > 0) & (grades >= 0))
    if ok.size == 0:
        return {k: np.array([], dtype=int) for k in ("a", "b", "cluster")} | {"gdiff": np.array([]), "w": np.array([])}
    order = ok[np.argsort(clusters[ok], kind="stable")]
    g = clusters[order]
    starts = np.flatnonzero(np.r_[True, g[1:] != g[:-1]])
    ends = np.r_[starts[1:], g.size]
    A, B, C = [], [], []
    for ci, (s, e) in enumerate(zip(starts, ends)):
        m = e - s
        if m < 2:
            continue
        ia, ib = np.triu_indices(m, 1)
        if ia.size > cap:
            pick = rng.choice(ia.size, cap, replace=False)
            ia, ib = ia[pick], ib[pick]
        A.append(order[s + ia])
        B.append(order[s + ib])
        C.append(np.full(ia.size, ci))
    if not A:
        return {k: np.array([], dtype=int) for k in ("a", "b", "cluster")} | {"gdiff": np.array([]), "w": np.array([])}
    a, b, c = np.concatenate(A), np.concatenate(B), np.concatenate(C)
    gdiff = (grades[a] - grades[b]).astype(np.float64)
    decisive = gdiff != 0
    per = np.bincount(c[decisive], minlength=c.max() + 1).astype(np.float64)
    w = np.where(decisive, 1.0 / np.maximum(per[c], 1), 0.0)
    return {"a": a, "b": b, "cluster": c, "gdiff": gdiff, "w": w}


def culling_metrics(
    score: np.ndarray,
    pairs: dict[str, np.ndarray],
    clusters: np.ndarray,
    grades: np.ndarray,
    *,
    b: int = DEFAULT_BOOTSTRAP,
    seed: int = 0,
    tie_eps: float = TIE_EPS,
) -> dict[str, Any]:
    """Within-cluster agreement of one score with graded culling labels."""
    a, bb, c, gdiff = pairs["a"], pairs["b"], pairs["cluster"], pairs["gdiff"]
    have = np.isfinite(score[a]) & np.isfinite(score[bb]) if a.size else np.array([], dtype=bool)
    a, bb, c, gdiff = a[have], bb[have], c[have], gdiff[have]
    out: dict[str, Any] = {"pairs": int(a.size)}
    if a.size == 0:
        return out
    ds = score[a] - score[bb]
    stie = np.abs(ds) <= tie_eps
    decisive = gdiff != 0
    agree = np.where(stie, 0.5, (np.sign(ds) == np.sign(gdiff)).astype(float))

    n_clu = int(c.max()) + 1
    dec_per = np.bincount(c[decisive], minlength=n_clu).astype(float)
    win_per = np.bincount(c[decisive], weights=agree[decisive], minlength=n_clu)
    has = dec_per > 0
    out["decisive_pairs"] = int(decisive.sum())
    out["label_tie_pairs"] = int((~decisive).sum())
    out["clusters"] = int(has.sum())
    out["score_tie_rate"] = _f(stie.mean())
    if has.any():
        macro = win_per[has] / dec_per[has]
        out["pairwise_accuracy_macro"] = _f(macro.mean())
        out["pairwise_accuracy_micro"] = _f(win_per.sum() / dec_per.sum())
        W = cluster_bootstrap_weights(np.arange(has.sum()), int(has.sum()), b, seed)
        boot = _boot_mean(W, macro)
        out["pairwise_accuracy_macro_ci"] = _ci(boot)

    # τ-b per cluster from pair signs (includes label ties).
    conc = np.sign(ds) * np.sign(gdiff)
    s_sum = np.bincount(c, weights=conc, minlength=n_clu)
    n_s = np.bincount(c, weights=(~stie).astype(float), minlength=n_clu)
    n_g = np.bincount(c, weights=decisive.astype(float), minlength=n_clu)
    tot = np.bincount(c, minlength=n_clu).astype(float)
    valid = (tot >= 3) & (n_s > 0) & (n_g > 0)
    if valid.any():
        tau = s_sum[valid] / np.sqrt(n_s[valid] * n_g[valid])
        out["kendall_tau_b_mean"] = _f(tau.mean())
        out["kendall_tau_b_clusters"] = int(valid.sum())
        W = cluster_bootstrap_weights(np.arange(valid.sum()), int(valid.sum()), b, seed + 1)
        out["kendall_tau_b_ci"] = _ci(_boot_mean(W, tau))

    out.update(_topk(score, clusters, grades, b=b, seed=seed + 2))
    return out


def _topk(score: np.ndarray, clusters: np.ndarray, grades: np.ndarray, *, b: int, seed: int) -> dict[str, Any]:
    ok = np.flatnonzero((clusters > 0) & (grades >= 0) & np.isfinite(score))
    if ok.size == 0:
        return {}
    order = ok[np.lexsort((-score[ok], clusters[ok]))]
    g = clusters[order]
    starts = np.flatnonzero(np.r_[True, g[1:] != g[:-1]])
    ends = np.r_[starts[1:], g.size]
    top1, nd1, nd3 = [], [], []
    for s, e in zip(starts, ends):
        if e - s < 2:
            continue
        gr = grades[order[s:e]].astype(float)
        if gr.max() == gr.min():
            continue
        top1.append(float(gr[0] == gr.max()))
        gains = 2**gr - 1
        ideal = np.sort(gains)[::-1]
        disc = 1 / np.log2(np.arange(2, gr.size + 2))
        for k, dst in ((1, nd1), (3, nd3)):
            kk = min(k, gr.size)
            idcg = (ideal[:kk] * disc[:kk]).sum()
            dst.append(float((gains[:kk] * disc[:kk]).sum() / idcg) if idcg > 0 else np.nan)
    if not top1:
        return {}
    out: dict[str, Any] = {"topk_clusters": len(top1)}
    for name, vals in (("top1_agreement", top1), ("ndcg_at_1", nd1), ("ndcg_at_3", nd3)):
        v = np.array(vals)
        out[name] = _f(np.nanmean(v))
        W = cluster_bootstrap_weights(np.arange(v.size), v.size, b, seed)
        out[f"{name}_ci"] = _ci(_boot_mean(W, np.nan_to_num(v)))
    return out


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(z, -35, 35)))


def fit_pairwise_logit(D: np.ndarray, y: np.ndarray, w: np.ndarray, *, l2: float = 1e-3, iters: int = 50) -> np.ndarray:
    """Intercept-free weighted logistic regression by Newton/IRLS (reversal-symmetric)."""
    k = D.shape[1]
    beta = np.zeros(k)
    sw = w.sum()
    for _ in range(iters):
        p = _sigmoid(D @ beta)
        grad = D.T @ (w * (p - y)) / sw + l2 * beta
        H = (D * (w * p * (1 - p))[:, None]).T @ D / sw + l2 * np.eye(k)
        step = np.linalg.solve(H, grad)
        beta -= step
        if np.abs(step).max() < 1e-8:
            break
    return beta


def _logit_eval(p: np.ndarray, y: np.ndarray, w: np.ndarray) -> dict[str, float]:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    sw = w.sum()
    bins = np.minimum((p * 10).astype(int), 9)
    ece = 0.0
    for bi in range(10):
        m = bins == bi
        if m.any():
            ece += w[m].sum() / sw * abs((w[m] @ p[m]) / w[m].sum() - (w[m] @ y[m]) / w[m].sum())
    return {
        "log_loss": float(-(w @ (y * np.log(p) + (1 - y) * np.log(1 - p))) / sw),
        "accuracy": float((w @ ((p > 0.5) == (y == 1))) / sw),
        "brier": float((w @ (p - y) ** 2) / sw),
        "ece": float(ece),
    }


def pairwise_logit_study(
    series: dict[str, np.ndarray],
    keys: list[str],
    pairs: dict[str, np.ndarray],
    *,
    folds: int = 5,
    seed: int = 0,
    l2: float = 1e-3,
) -> dict[str, Any]:
    """Grouped-CV pairwise logistic model over Δⱼ, with drop-one ablation and single-model baselines."""
    a, b, c, gdiff, w = pairs["a"], pairs["b"], pairs["cluster"], pairs["gdiff"], pairs["w"]
    decisive = gdiff != 0
    if not decisive.any() or not keys:
        return {"pairs": 0}
    D_all = np.column_stack([series[k][a] - series[k][b] for k in keys])
    ok = decisive & np.isfinite(D_all).all(axis=1)
    D, y, cl, ww = D_all[ok], (gdiff[ok] > 0).astype(float), c[ok], w[ok]
    if D.shape[0] < 50:
        return {"pairs": int(D.shape[0]), "skipped": "fewer than 50 decisive pairs with all models"}
    scale = D.std(axis=0)
    scale[scale == 0] = 1.0
    Z = D / scale
    rng = np.random.default_rng(seed)
    uc = np.unique(cl)
    fold_of = dict(zip(uc.tolist(), rng.permutation(uc.size) % folds))
    fid = np.array([fold_of[x] for x in cl.tolist()])

    def cv(cols: list[int]) -> dict[str, float]:
        pred = np.empty(y.size)
        for f in range(folds):
            tr, te = fid != f, fid == f
            if not te.any() or not tr.any():
                continue
            beta = fit_pairwise_logit(Z[tr][:, cols], y[tr], ww[tr], l2=l2)
            pred[te] = _sigmoid(Z[te][:, cols] @ beta)
        return _logit_eval(pred, y, ww)

    all_cols = list(range(len(keys)))
    full = cv(all_cols)
    beta_full = fit_pairwise_logit(Z, y, ww, l2=l2)
    ablation = []
    for j, key in enumerate(keys):
        single = cv([j])
        drop = cv([x for x in all_cols if x != j]) if len(keys) > 1 else None
        ablation.append(
            {
                "dimension": key,
                "beta_std": float(beta_full[j]),
                "beta_raw": float(beta_full[j] / scale[j]),
                "single_log_loss": single["log_loss"],
                "single_accuracy": single["accuracy"],
                "drop_log_loss": drop["log_loss"] if drop else None,
                "marginal_log_loss_gain": (drop["log_loss"] - full["log_loss"]) if drop else None,
            }
        )
    return {
        "pairs": int(y.size),
        "clusters": int(uc.size),
        "folds": folds,
        "l2": l2,
        "equation": "P(a ≻ b) = σ(Σ_j β_j · Δ_j(a,b))  (no intercept; Δ standardized by pooled SD)",
        "cv": full,
        "coefficients": ablation,
    }


# ---------------------------------------------------------------------------
# global agreement (G_j)
# ---------------------------------------------------------------------------


def global_metrics(
    score: np.ndarray,
    label: np.ndarray,
    clusters: np.ndarray,
    *,
    b: int = DEFAULT_BOOTSTRAP,
    seed: int = 0,
) -> dict[str, Any]:
    """Burst-downweighted Spearman between a score and an independent global label.

    Each image weighs 1/|cluster| (standalone images weigh 1) so large bursts
    cannot dominate; CI from a cluster bootstrap on fixed global ranks.
    """
    ok = np.isfinite(score) & np.isfinite(label)
    n = int(ok.sum())
    if n < 30:
        return {"n": n}
    s, lab, g = score[ok], label[ok], singleton_groups(clusters[ok])
    codes, sizes = group_index(g)
    base_w = 1.0 / sizes[codes]
    rs, rl = average_ranks(s), average_ranks(lab)
    rho = float(_weighted_pearson(rs, rl, base_w[None, :])[0])
    W = cluster_bootstrap_weights(codes, sizes.size, b, seed)[:, codes] * base_w[None, :]
    boot = _weighted_pearson(rs, rl, W)
    unweighted = sps.spearmanr(s, lab)
    return {
        "n": n,
        "clusters": int(sizes.size),
        "spearman_weighted": _f(rho),
        "spearman_weighted_ci": _ci(boot),
        "spearman_unweighted": _f(unweighted.statistic),
        "spearman_unweighted_p": _f(unweighted.pvalue),
    }


def ridge_global(
    series: dict[str, np.ndarray], keys: list[str], label: np.ndarray, clusters: np.ndarray, *, folds: int = 5, l2: float = 1.0, seed: int = 0
) -> dict[str, Any]:
    """Candidate Q_global = ridge regression of the global label on standardized scores (grouped CV)."""
    X = np.column_stack([series[k] for k in keys])
    ok = np.isfinite(label) & np.isfinite(X).all(axis=1)
    if ok.sum() < 50:
        return {"n": int(ok.sum())}
    X, y, g = X[ok], label[ok], singleton_groups(clusters[ok])
    mu, sd = X.mean(axis=0), np.where(X.std(axis=0) > 0, X.std(axis=0), 1)
    Z = (X - mu) / sd
    rng = np.random.default_rng(seed)
    uc, codes = np.unique(g, return_inverse=True)
    fid = rng.permutation(uc.size)[codes] % folds

    def fit(Zt, yt):
        A = np.column_stack([np.ones(len(yt)), Zt])
        reg = l2 * np.eye(A.shape[1])
        reg[0, 0] = 0
        return np.linalg.solve(A.T @ A + reg, A.T @ yt)

    pred = np.empty(y.size)
    for f in range(folds):
        tr, te = fid != f, fid == f
        if te.any() and tr.any():
            beta = fit(Z[tr], y[tr])
            pred[te] = np.column_stack([np.ones(te.sum()), Z[te]]) @ beta
    beta = fit(Z, y)
    return {
        "n": int(y.size),
        "equation": "Q_global = β0 + Σ_j β_j · z_j  (z = standardized score; ridge, grouped CV by cluster)",
        "intercept": float(beta[0]),
        "weights_std": {k: float(v) for k, v in zip(keys, beta[1:])},
        "cv_spearman": _f(sps.spearmanr(pred, y).statistic),
        "cv_mae": float(np.abs(pred - y).mean()),
    }


# ---------------------------------------------------------------------------
# 10. suitability map
# ---------------------------------------------------------------------------


def suitability_map(
    keys: list[str],
    kinds: dict[str, str],
    global_by_key: dict[str, dict[str, Any]],
    culling_by_key: dict[str, dict[str, Any]],
    *,
    global_min: float,
    culling_min: float,
    global_independent: bool,
    culling_independent: bool,
) -> list[dict[str, Any]]:
    """Uⱼ = (Gⱼ, Cⱼ) with membership from lower CI bounds vs prespecified thresholds."""
    rows = []
    for k in keys:
        g = global_by_key.get(k, {})
        c = culling_by_key.get(k, {})
        g_ci = g.get("spearman_weighted_ci") or (None, None)
        c_ci = c.get("pairwise_accuracy_macro_ci") or (None, None)
        in_a = None if g_ci[0] is None else g_ci[0] >= global_min
        in_b = None if c_ci[0] is None else c_ci[0] >= culling_min
        caveats = []
        if kinds.get(k) == "composite":
            caveats.append("derived from component models — not an independent model")
        if kinds.get(k) == "shadow":
            caveats.append("shadow model")
        if in_a is not None and not global_independent:
            caveats.append("global labels not verified independent")
        if in_b is not None and not culling_independent:
            caveats.append("culling labels not verified independent")
        if in_a is None:
            caveats.append("insufficient global labels")
        if in_b is None:
            caveats.append("insufficient culling labels")
        if in_a and in_b:
            role = "both"
        elif in_a:
            role = "global"
        elif in_b:
            role = "culling"
        elif in_a is None and in_b is None:
            role = "unknown"
        else:
            role = "neither"
        rows.append(
            {
                "dimension": k,
                "kind": kinds.get(k),
                "G": g.get("spearman_weighted"),
                "G_ci": list(g_ci),
                "G_n": g.get("n"),
                "C": c.get("pairwise_accuracy_macro"),
                "C_ci": list(c_ci),
                "C_clusters": c.get("clusters"),
                "in_Na": in_a,
                "in_Nb": in_b,
                "role": role,
                "provisional": bool((in_a is not None and not global_independent) or (in_b is not None and not culling_independent)),
                "caveats": caveats,
            }
        )
    return rows


def size_bucket(size: int) -> str:
    if size <= 2:
        return "2"
    if size <= 4:
        return "3-4"
    if size <= 8:
        return "5-8"
    return "9+"
