"""Multivariate analysis for Everypixel UGC vs local scoring dimensions.

Methodology follows standard scoring-dimension modeling: descriptives, pairwise
correlation (Pearson + Spearman), VIF multicollinearity, OLS regression with
R² / adjusted R² / RMSE, and incremental prediction tests.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import pearsonr, spearmanr, t as student_t

from scripts.research.everypixel_correlation.common import (
    COMPOSITE_COLUMNS,
    CORE_MODEL_NAMES,
)

LOCAL_PREDICTORS = list(COMPOSITE_COLUMNS) + list(CORE_MODEL_NAMES)


def _matrix_from_joined(
    joined: list[dict[str, Any]],
    columns: list[str],
) -> tuple[np.ndarray, list[str]]:
    """Drop rows with any missing value in ``columns``."""
    rows: list[list[float]] = []
    for item in joined:
        vals: list[float] = []
        ok = True
        for col in columns:
            v = item.get(col)
            if v is None:
                ok = False
                break
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                ok = False
                break
        if ok:
            rows.append(vals)
    if not rows:
        return np.empty((0, len(columns))), columns
    return np.asarray(rows, dtype=float), columns


def descriptive_stats(joined: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for col in columns:
        xs = []
        for row in joined:
            v = row.get(col)
            if v is None:
                continue
            try:
                xs.append(float(v))
            except (TypeError, ValueError):
                continue
        if len(xs) < 2:
            continue
        arr = np.asarray(xs, dtype=float)
        q1, q2, q3 = np.percentile(arr, [25, 50, 75])
        out.append(
            {
                "variable": col,
                "n": len(arr),
                "mean": round(float(np.mean(arr)), 6),
                "std": round(float(np.std(arr, ddof=1)), 6),
                "min": round(float(np.min(arr)), 6),
                "q1": round(float(q1), 6),
                "median": round(float(q2), 6),
                "q3": round(float(q3), 6),
                "max": round(float(np.max(arr)), 6),
                "skewness": round(float(_skew(arr)), 4),
            }
        )
    return out


def _skew(arr: np.ndarray) -> float:
    n = len(arr)
    if n < 3:
        return float("nan")
    m = np.mean(arr)
    s = np.std(arr, ddof=1)
    if s == 0:
        return 0.0
    return float(np.mean(((arr - m) / s) ** 3))


def predictor_correlation_matrix(
    joined: list[dict[str, Any]],
    columns: list[str],
) -> list[dict[str, Any]]:
    """Pairwise Pearson and Spearman among predictors (+ UGC targets if present)."""
    rows_out: list[dict[str, Any]] = []
    for i, a in enumerate(columns):
        for b in columns[i + 1 :]:
            xa, xb = _paired(joined, a, b)
            n = len(xa)
            if n < 3:
                continue
            pr, pp = pearsonr(xa, xb)
            sr, sp = spearmanr(xa, xb)
            rows_out.append(
                {
                    "var_a": a,
                    "var_b": b,
                    "n": n,
                    "pearson_r": round(float(pr), 4),
                    "pearson_p": round(float(pp), 6) if pp == pp else "",
                    "spearman_r": round(float(sr), 4),
                    "spearman_p": round(float(sp), 6) if sp == sp else "",
                }
            )
    return rows_out


def _paired(joined: list[dict[str, Any]], a: str, b: str) -> tuple[np.ndarray, np.ndarray]:
    xs: list[float] = []
    ys: list[float] = []
    for row in joined:
        try:
            xs.append(float(row[a]))
            ys.append(float(row[b]))
        except (KeyError, TypeError, ValueError):
            continue
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)


def variance_inflation_factors(X: np.ndarray, names: list[str]) -> list[dict[str, Any]]:
    """VIF via auxiliary R² of each column on the others."""
    if X.shape[0] < X.shape[1] + 2:
        return []
    out: list[dict[str, Any]] = []
    for j, name in enumerate(names):
        y = X[:, j]
        others = np.delete(X, j, axis=1)
        ones = np.ones((others.shape[0], 1))
        design = np.hstack([ones, others])
        beta, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
        y_hat = design @ beta
        ss_res = float(np.sum((y - y_hat) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        vif = 1.0 / (1.0 - r2) if r2 < 1.0 else float("inf")
        flag = "high" if vif > 10 else ("moderate" if vif > 5 else "ok")
        out.append({"predictor": name, "vif": round(vif, 4), "aux_r2": round(r2, 4), "flag": flag})
    return out


def ols_fit(
    y: np.ndarray,
    X: np.ndarray,
    predictor_names: list[str],
) -> dict[str, Any]:
    """OLS with intercept; returns metrics and coefficient table."""
    n = X.shape[0]
    p = X.shape[1] + 1  # with intercept
    if n <= p:
        return {"error": "insufficient_n", "n": n, "predictors": predictor_names}

    ones = np.ones((n, 1))
    design = np.hstack([ones, X])
    beta, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    y_hat = design @ beta
    resid = y - y_hat
    ss_res = float(resid @ resid)
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / (n - p) if n > p else float("nan")
    rmse = float(np.sqrt(ss_res / n))
    mse = ss_res / (n - p)
    try:
        cov = mse * np.linalg.inv(design.T @ design)
        se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    except np.linalg.LinAlgError:
        se = np.full(p, float("nan"))

    df = n - p
    coef_rows = [{"term": "intercept", "beta": round(float(beta[0]), 6), "se": round(float(se[0]), 6)}]
    for i, name in enumerate(predictor_names, start=1):
        t_stat = beta[i] / se[i] if se[i] > 0 else float("nan")
        p_val = (
            float(2 * (1 - student_t.cdf(abs(t_stat), df)))
            if t_stat == t_stat and df > 0
            else float("nan")
        )
        coef_rows.append(
            {
                "term": name,
                "beta": round(float(beta[i]), 6),
                "se": round(float(se[i]), 6),
                "t": round(float(t_stat), 4) if t_stat == t_stat else "",
                "p_value": round(p_val, 6) if p_val == p_val else "",
            }
        )
    return {
        "n": n,
        "r2": round(r2, 4),
        "adj_r2": round(adj_r2, 4),
        "rmse": round(rmse, 6),
        "coefficients": coef_rows,
    }


def run_modeling_suite(joined: list[dict[str, Any]]) -> dict[str, Any]:
    """Full analysis pass aligned with multivariate scoring-dimension workflow."""
    ugc_cols = ["ugc_score", "ugc_class"]
    all_vars = ugc_cols + LOCAL_PREDICTORS
    desc = descriptive_stats(joined, [c for c in all_vars if _has_any(joined, c)])
    pred_corr = predictor_correlation_matrix(
        joined, [c for c in LOCAL_PREDICTORS + ["ugc_score"] if _has_any(joined, c)]
    )

    X_full, names = _matrix_from_joined(joined, LOCAL_PREDICTORS)
    vif = variance_inflation_factors(X_full, names) if X_full.size else []

    y_score, Xs = _matrix_from_joined(joined, ["ugc_score"] + LOCAL_PREDICTORS)
    model_ugc_from_local = {}
    if y_score.shape[0] >= len(LOCAL_PREDICTORS) + 5:
        model_ugc_from_local = ols_fit(y_score[:, 0], y_score[:, 1:], LOCAL_PREDICTORS)

    # Incremental: score_general ~ liqe + topiq vs + ugc_score
    inc_base_cols = ["liqe", "topiq"]
    inc_cols = inc_base_cols + ["ugc_score"]
    y_gen, M = _matrix_from_joined(joined, ["score_general"] + inc_cols)
    incremental: dict[str, Any] = {}
    if y_gen.shape[0] >= 20:
        m0 = ols_fit(y_gen[:, 0], y_gen[:, 1:3], inc_base_cols)
        m1 = ols_fit(y_gen[:, 0], y_gen[:, 1:], inc_cols)
        incremental = {
            "baseline_predictors": inc_base_cols,
            "extended_predictors": inc_cols,
            "baseline_r2": m0.get("r2"),
            "extended_r2": m1.get("r2"),
            "delta_r2": round(float(m1.get("r2", 0)) - float(m0.get("r2", 0)), 4)
            if "r2" in m0 and "r2" in m1
            else None,
            "ugc_score_coef": next(
                (c for c in m1.get("coefficients", []) if c.get("term") == "ugc_score"),
                None,
            ),
        }

    y_class, Xc = _matrix_from_joined(joined, ["ugc_class"] + LOCAL_PREDICTORS)
    model_class_from_local = {}
    if y_class.shape[0] >= len(LOCAL_PREDICTORS) + 5:
        model_class_from_local = ols_fit(y_class[:, 0], y_class[:, 1:], LOCAL_PREDICTORS)

    return {
        "descriptive": desc,
        "predictor_correlations": pred_corr,
        "vif": vif,
        "ols_ugc_score_from_local": model_ugc_from_local,
        "ols_ugc_class_from_local": model_class_from_local,
        "incremental_score_general": incremental,
    }


def _has_any(joined: list[dict[str, Any]], col: str) -> bool:
    return any(row.get(col) is not None for row in joined)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_joined_csv(path: Path, joined: list[dict[str, Any]]) -> None:
    if not joined:
        return
    cols = list(joined[0].keys())
    write_csv(path, cols, joined)


def write_modeling_artifacts(out_dir: Path, suite: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        out_dir / "descriptive_stats.csv",
        ["variable", "n", "mean", "std", "min", "q1", "median", "q3", "max", "skewness"],
        suite.get("descriptive") or [],
    )
    write_csv(
        out_dir / "predictor_correlation_pairs.csv",
        ["var_a", "var_b", "n", "pearson_r", "pearson_p", "spearman_r", "spearman_p"],
        suite.get("predictor_correlations") or [],
    )
    write_csv(
        out_dir / "vif_predictors.csv",
        ["predictor", "vif", "aux_r2", "flag"],
        suite.get("vif") or [],
    )
    json_path = out_dir / "regression_models.json"
    json_path.write_text(
        json.dumps(
            {
                "ols_ugc_score_from_local": suite.get("ols_ugc_score_from_local"),
                "ols_ugc_class_from_local": suite.get("ols_ugc_class_from_local"),
                "incremental_score_general": suite.get("incremental_score_general"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return write_modeling_summary_md(out_dir / "modeling_summary.md", suite)


def write_modeling_summary_md(path: Path, suite: dict[str, Any]) -> Path:
    vif = suite.get("vif") or []
    high_vif = [v for v in vif if v.get("flag") == "high"]
    inc = suite.get("incremental_score_general") or {}
    m_score = suite.get("ols_ugc_score_from_local") or {}
    m_class = suite.get("ols_ugc_class_from_local") or {}

    lines = [
        "# Everypixel study — multivariate modeling summary",
        "",
        "Protocol: descriptive stats → pairwise correlation → VIF → OLS regression "
        "(see study planning doc § Statistical protocol).",
        "",
        "## Multicollinearity (VIF on local predictors)",
        "",
    ]
    if vif:
        lines.append("| predictor | VIF | aux R² | flag |")
        lines.append("|-----------|----:|-------:|------|")
        for v in vif:
            lines.append(
                f"| {v['predictor']} | {v['vif']} | {v['aux_r2']} | {v['flag']} |"
            )
    else:
        lines.append("_Insufficient complete rows for VIF._")
    lines.extend(["", f"Predictors with VIF > 10: **{len(high_vif)}**.", ""])

    lines.extend(["## OLS: predict `ugc_score` from local dimensions", ""])
    if m_score and "r2" in m_score:
        lines.append(
            f"- n={m_score['n']}, R²={m_score['r2']}, adj R²={m_score['adj_r2']}, RMSE={m_score['rmse']}"
        )
        lines.append("")
        lines.append("| term | β | p |")
        lines.append("|------|---:|---:|")
        for c in m_score.get("coefficients") or []:
            if c.get("term") == "intercept":
                continue
            lines.append(f"| {c['term']} | {c.get('beta', '')} | {c.get('p_value', '')} |")
    else:
        lines.append("_Model not fit (missing data or n too small)._")

    lines.extend(["", "## OLS: predict `ugc_class` from local dimensions (screening)", ""])
    if m_class and "r2" in m_class:
        lines.append(
            f"- n={m_class['n']}, R²={m_class['r2']}, adj R²={m_class['adj_r2']}, RMSE={m_class['rmse']}"
        )
        lines.append(
            "- Treat as exploratory only (`ugc_class` is ordinal 1–5; Spearman remains primary)."
        )
    else:
        lines.append("_Model not fit._")

    lines.extend(["", "## Incremental value for `score_general`", ""])
    if inc:
        lines.append(
            f"- Baseline ({', '.join(inc.get('baseline_predictors') or [])}): R²={inc.get('baseline_r2')}"
        )
        lines.append(
            f"- + `ugc_score`: R²={inc.get('extended_r2')}, ΔR²={inc.get('delta_r2')}"
        )
        uc = inc.get("ugc_score_coef") or {}
        if uc:
            lines.append(f"- `ugc_score` coefficient p={uc.get('p_value')} (holding liqe, topiq fixed)")
    else:
        lines.append("_Incremental model not fit._")

    lines.extend(
        [
            "",
            "## Feature adjustment hints (from modeling pass)",
            "",
            "- Drop or regularize predictors with **VIF > 10** before trusting individual OLS coefficients.",
            "- **SPAQ** was weak vs UGC in Spearman; check VIF vs **AVA/LIQE** before fusion decisions.",
            "- Do not promote Everypixel to fusion on R² alone — rendition confound (embedded JPEG vs pipeline).",
            "",
            "Artifacts: `descriptive_stats.csv`, `predictor_correlation_pairs.csv`, "
            "`vif_predictors.csv`, `regression_models.json`.",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
