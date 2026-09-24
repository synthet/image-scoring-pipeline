"""Endpoint-level payloads for score analytics (cached per matrix fingerprint).

Every payload can be computed on a *layer*: the full library or the subset of
images tagged with one keyword. The stacks payload analyses culling signals
inside stacks of that layer.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from modules.score_analytics import data, stacks, stats


class ScoreAnalyticsInputError(Exception):
    """Invalid request parameters (unknown dimension, too few complete rows)."""


def compute_stats(m: data.ScoreMatrix) -> dict[str, Any]:
    return {
        "fingerprint": m.fingerprint,
        "generated_at": m.generated_at,
        "scope": m.scope,
        "image_count": m.image_count,
        "keys": m.keys,
        "meta": m.meta,
        "descriptives": {k: stats.describe(m.series[k], m.image_count) for k in m.keys},
        "correlation": stats.correlations(m.series, m.keys),
    }


def get_stats(keyword: str | None = None) -> dict[str, Any]:
    kw = data.normalize_keyword(keyword)
    return data.cached(("stats", kw), lambda _m: compute_stats(data.get_scoped(kw)))


def default_predictors(m: data.ScoreMatrix, target: str) -> list[str]:
    return [k for k in m.keys if m.meta[k]["kind"] == "model" and k != target]


def resolve_regression_inputs(
    m: data.ScoreMatrix, target: str, predictors: list[str] | None
) -> list[str]:
    if target not in m.series:
        raise ScoreAnalyticsInputError(f"Unknown target '{target}'. Available: {', '.join(m.keys)}")
    preds = list(dict.fromkeys(predictors)) if predictors else default_predictors(m, target)
    unknown = [p for p in preds if p not in m.series]
    if unknown:
        raise ScoreAnalyticsInputError(f"Unknown predictor(s): {', '.join(unknown)}")
    if target in preds:
        raise ScoreAnalyticsInputError("Target cannot also be a predictor")
    if not preds:
        raise ScoreAnalyticsInputError("At least one predictor is required")
    return preds


def get_regression(
    target: str, predictors: list[str] | None, keyword: str | None = None
) -> dict[str, Any]:
    kw = data.normalize_keyword(keyword)
    m = data.get_scoped(kw)
    preds = resolve_regression_inputs(m, target, predictors)
    return data.cached(
        ("regression", kw, target, tuple(preds)), lambda _m: compute_regression(m, target, preds)
    )


def compute_regression(m: data.ScoreMatrix, target: str, preds: list[str]) -> dict[str, Any]:
    y_all = m.series[target]
    X_all = np.column_stack([m.series[p] for p in preds])
    complete = np.isfinite(y_all) & np.isfinite(X_all).all(axis=1)
    n = int(complete.sum())
    need = max(stats.MIN_REGRESSION_ROWS, len(preds) + 2)
    if n < need:
        raise ScoreAnalyticsInputError(
            f"Only {n} images have scores for '{target}' and all predictors; need at least {need}."
        )
    y, X = y_all[complete], X_all[complete]
    fit = stats.ols(y, X, preds)

    weights = _configured_weights(target)
    for c in fit["coefficients"]:
        c["configured_weight"] = weights.get(c["name"]) if weights is not None else None

    return {
        "fingerprint": m.fingerprint,
        "scope": m.scope,
        "target": target,
        "predictors": preds,
        "complete_rows": n,
        "image_count": m.image_count,
        "configured_weights": weights,
        **fit,
        "recommendations": stats.recommendations(preds, X, y, target, fit),
    }


def compute_stacks(m: data.ScoreMatrix, min_size: int, per_stack: bool = False) -> dict[str, Any]:
    result = stacks.analyze_stacks(
        m.series,
        m.keys,
        m.stack_ids,
        m.pick_status,
        m.image_ids,
        m.best_image_by_stack,
        min_size=min_size,
        per_stack=per_stack,
    )
    return {
        "fingerprint": m.fingerprint,
        "scope": m.scope,
        "image_count": m.image_count,
        "meta": m.meta,
        **result,
    }


def get_stacks(keyword: str | None = None, min_size: int = stacks.DEFAULT_MIN_STACK_SIZE) -> dict[str, Any]:
    if min_size < 2:
        raise ScoreAnalyticsInputError("min_size must be at least 2")
    kw = data.normalize_keyword(keyword)
    return data.cached(("stacks", kw, min_size), lambda _m: compute_stacks(data.get_scoped(kw), min_size))


def keyword_profile(full: data.ScoreMatrix, layer: data.ScoreMatrix) -> list[dict[str, Any]]:
    """Per-dimension stats of a keyword layer vs the rest of the library.

    ``cohens_d`` > 0 means the layer scores higher than the rest; ``rank_shift``
    is the layer's mean percentile within the full library minus 0.5.
    """
    in_layer = np.isin(full.image_ids, layer.image_ids)
    rows = []
    for key in layer.keys:
        x_all = full.series[key]
        ok = np.isfinite(x_all)
        a, b = x_all[ok & in_layer], x_all[ok & ~in_layer]
        d = stats.describe(a, layer.image_count)
        pooled = None
        if a.size > 1 and b.size > 1:
            pooled = np.sqrt(((a.size - 1) * a.var(ddof=1) + (b.size - 1) * b.var(ddof=1)) / (a.size + b.size - 2))
        ranks = np.argsort(np.argsort(x_all[ok])) / max(ok.sum() - 1, 1)
        rows.append(
            {
                "dimension": key,
                "count": d["count"],
                "coverage_pct": d.get("coverage_pct"),
                "mean": d.get("mean"),
                "median": d.get("median"),
                "std": d.get("std"),
                "iqr": d.get("iqr"),
                "skewness": d.get("skewness"),
                "rest_mean": stats.finite_or_none(b.mean()) if b.size else None,
                "mean_delta": stats.finite_or_none(a.mean() - b.mean()) if a.size and b.size else None,
                "cohens_d": stats.finite_or_none((a.mean() - b.mean()) / pooled) if pooled else None,
                "rank_shift": stats.finite_or_none(ranks[in_layer[ok]].mean() - 0.5) if a.size else None,
            }
        )
    return rows


def get_keyword_profiles(limit: int = 20, min_images: int = 30) -> dict[str, Any]:
    def compute(m: data.ScoreMatrix) -> dict[str, Any]:
        out = []
        for keyword, count in data.top_keywords(limit, min_images):
            layer = data.scope_matrix(m, keyword)
            out.append({"keyword": keyword, "images": count, "dimensions": keyword_profile(m, layer)})
        return {"fingerprint": m.fingerprint, "image_count": m.image_count, "keys": m.keys, "keywords": out}

    return data.cached(("keyword_profiles", limit, min_images), compute)


def _configured_weights(target: str) -> dict[str, float] | None:
    from modules.score_normalization import get_composite_weights

    weights = get_composite_weights().get(target)
    if not isinstance(weights, dict):
        return None
    return {str(k): float(v) for k, v in weights.items()}
