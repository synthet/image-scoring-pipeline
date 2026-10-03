"""Turn fetched /api/analytics/scores payloads into CSV tables and SUMMARY.md."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_DIR = ROOT / "csv"

LABELS = {
    "general": "General",
    "technical": "Technical",
    "aesthetic": "Aesthetic",
    "arniqa": "ARNIQA",
    "ava": "AVA",
    "clip_quality_v0": "CLIP Quality",
    "liqe": "LIQE",
    "spaq": "SPAQ",
    "topiq": "TOPIQ-NR",
}


def label(key: str) -> str:
    return LABELS.get(key, key)


def load(name: str) -> dict:
    with (ROOT / f"{name}.json").open(encoding="utf-8") as f:
        return json.load(f)


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_square(path: Path, keys: list[str], matrix: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["dimension", *keys])
        for i, key in enumerate(keys):
            writer.writerow([key, *matrix[i]])


def fmt(value, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    if isinstance(value, float):
        if abs(value) >= 1000:
            return f"{value:,.1f}"
        return f"{value:.{digits}f}"
    return str(value)


def ci(pair) -> str:
    if not pair or pair[0] is None or pair[1] is None:
        return "—"
    return f"{pair[0]:.3f}–{pair[1]:.3f}"


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def pairs_from_square(keys: list[str], matrix: list[list], *, abs_min: float = 0.0) -> list[tuple]:
    out = []
    for i, a in enumerate(keys):
        for j in range(i + 1, len(keys)):
            value = matrix[i][j]
            if value is None:
                continue
            if abs(value) >= abs_min:
                out.append((a, keys[j], value))
    out.sort(key=lambda item: abs(item[2]), reverse=True)
    return out


def main() -> None:
    stats = load("stats")
    matrix = load("matrix")
    regression = load("regression")
    stacks = load("stacks")
    keywords = load("keywords")
    suitability = load("suitability")

    keys: list[str] = stats["keys"]
    meta = stats["meta"]
    descriptives = stats["descriptives"]

    write_rows(
        CSV_DIR / "coverage.csv",
        [
            {
                "dimension": key,
                "label": label(key),
                "kind": meta[key]["kind"],
                "count": meta[key]["count"],
                "coverage_pct": meta[key]["coverage_pct"],
            }
            for key in keys
        ],
    )

    desc_rows = []
    hist_rows = []
    for key in keys:
        desc = descriptives[key]
        hist = desc["histogram"]
        row = {
            "dimension": key,
            "label": label(key),
            "kind": meta[key]["kind"],
            **{k: desc[k] for k in desc if k != "histogram"},
        }
        desc_rows.append(row)
        width = (hist["hi"] - hist["lo"]) / len(hist["counts"]) if hist["counts"] else None
        for i, count in enumerate(hist["counts"]):
            lo = hist["lo"] + i * width
            hist_rows.append(
                {
                    "dimension": key,
                    "bin": i,
                    "lo": lo,
                    "hi": lo + width,
                    "count": count,
                }
            )
    write_rows(CSV_DIR / "descriptives.csv", desc_rows)
    write_rows(CSV_DIR / "histograms.csv", hist_rows)

    corr = stats["correlation"]
    for name in ("pearson", "pearson_p", "spearman", "spearman_p", "n"):
        write_square(CSV_DIR / f"correlation_{name}.csv", keys, corr[name])

    # Rank-curve source: one row per image. Curves are this matrix sorted by a dimension.
    series = matrix["series"]
    with (CSV_DIR / "scores_matrix.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["image_id", *keys])
        ids = matrix["image_ids"]
        columns = [series[key] for key in keys]
        for i, image_id in enumerate(ids):
            writer.writerow([image_id, *[col[i] for col in columns]])

    decile_rows = []
    for picked in keys:
        indexed = [(i, series[picked][i]) for i in range(len(ids)) if series[picked][i] is not None]
        indexed.sort(key=lambda item: (item[1], item[0]))
        n = len(indexed)
        if n == 0:
            continue
        for decile in range(10):
            start = decile * n // 10
            end = (decile + 1) * n // 10
            chunk = indexed[start:end]
            for key in keys:
                vals = [series[key][i] for i, _ in chunk if series[key][i] is not None]
                decile_rows.append(
                    {
                        "ranked_by": picked,
                        "decile": decile + 1,
                        "decile_lo_score": chunk[0][1],
                        "decile_hi_score": chunk[-1][1],
                        "images": len(chunk),
                        "dimension": key,
                        "n": len(vals),
                        "mean": (sum(vals) / len(vals)) if vals else None,
                    }
                )
    write_rows(CSV_DIR / "rank_curve_deciles.csv", decile_rows)

    residuals = regression["residuals"]
    write_rows(
        CSV_DIR / "regression_fit.csv",
        [
            {
                "target": regression["target"],
                "predictors": ",".join(regression["predictors"]),
                "image_count": regression["image_count"],
                "complete_rows": regression["complete_rows"],
                "n": regression["n"],
                "k": regression["k"],
                "dof": regression["dof"],
                "rank_deficient": regression["rank_deficient"],
                "intercept": regression["intercept"]["beta"],
                "intercept_se": regression["intercept"]["se"],
                "intercept_t": regression["intercept"]["t"],
                "intercept_p": regression["intercept"]["p"],
                "intercept_ci_lo": regression["intercept"].get("ci_lo"),
                "intercept_ci_hi": regression["intercept"].get("ci_hi"),
                "r2": regression["r2"],
                "adj_r2": regression["adj_r2"],
                "cv_r2": regression["cv_r2"],
                "rmse": regression["rmse"],
                "mae": regression["mae"],
                "f_stat": regression["f_stat"],
                "f_p": regression["f_p"],
                "residual_sample": residuals.get("sampled"),
            }
        ],
    )
    write_rows(CSV_DIR / "regression_coefficients.csv", regression["coefficients"])
    write_rows(CSV_DIR / "regression_recommendations.csv", regression.get("recommendations") or [])
    hist = residuals["histogram"]
    width = (hist["hi"] - hist["lo"]) / len(hist["counts"]) if hist["counts"] else None
    write_rows(
        CSV_DIR / "regression_residual_histogram.csv",
        [
            {"bin": i, "lo": hist["lo"] + i * width, "hi": hist["lo"] + (i + 1) * width, "count": count}
            for i, count in enumerate(hist["counts"])
        ],
    )
    write_rows(
        CSV_DIR / "regression_residuals_sample.csv",
        [
            {"fitted": fitted, "residual": residual}
            for fitted, residual in zip(residuals["fitted"], residuals["residual"])
        ],
    )

    write_rows(
        CSV_DIR / "stacks_overview.csv",
        [
            {
                "image_count": stacks["image_count"],
                "min_size": stacks["min_size"],
                "tie_eps": stacks.get("tie_eps"),
                "stacks_considered": stacks["stacks_considered"],
                "images_in_stacks": stacks["images_in_stacks"],
                "stacks_with_picks": stacks["stacks_with_picks"],
                "ranking": ",".join(stacks["ranking"]),
            }
        ],
    )
    write_rows(CSV_DIR / "stacks_signals.csv", stacks["models"])
    agreement = stacks["agreement"]
    write_square(CSV_DIR / "stacks_agreement_spearman.csv", stacks["keys"], agreement["spearman"])
    write_square(CSV_DIR / "stacks_agreement_n.csv", stacks["keys"], agreement["stacks"])

    keyword_rows = []
    for entry in keywords["keywords"]:
        for dim in entry["dimensions"]:
            keyword_rows.append({"keyword": entry["keyword"], "keyword_images": entry["images"], **dim})
    write_rows(CSV_DIR / "keywords.csv", keyword_rows)

    suit_map = suitability["suitability"]["map"]
    map_rows = []
    for row in suit_map:
        flat = {k: v for k, v in row.items() if k not in ("G_ci", "C_ci", "caveats")}
        flat["G_ci_lo"], flat["G_ci_hi"] = (row.get("G_ci") or [None, None])[:2]
        flat["C_ci_lo"], flat["C_ci_hi"] = (row.get("C_ci") or [None, None])[:2]
        flat["caveats"] = "; ".join(row.get("caveats") or [])
        map_rows.append(flat)
    write_rows(CSV_DIR / "suitability_map.csv", map_rows)

    profile_rows = []
    ecdf_rows = []
    qq_rows = []
    for key, profile in suitability["profiles"].items():
        flat = {"dimension": key}
        for field, value in profile.items():
            if field in ("ecdf", "qq_normal", "percentiles", "mean_ci", "median_ci"):
                continue
            flat[field] = value
        for pct, value in (profile.get("percentiles") or {}).items():
            flat[f"p{pct}"] = value
        mean_ci = profile.get("mean_ci") or [None, None]
        median_ci = profile.get("median_ci") or [None, None]
        flat["mean_ci_lo"], flat["mean_ci_hi"] = mean_ci[0], mean_ci[1]
        flat["median_ci_lo"], flat["median_ci_hi"] = median_ci[0], median_ci[1]
        profile_rows.append(flat)
        ecdf = profile.get("ecdf") or {}
        for p, q in zip(ecdf.get("p") or [], ecdf.get("q") or []):
            ecdf_rows.append({"dimension": key, "p": p, "q": q})
        qq = profile.get("qq_normal") or {}
        for theoretical, sample in zip(qq.get("theoretical") or [], qq.get("sample") or []):
            qq_rows.append({"dimension": key, "theoretical": theoretical, "sample": sample})
    write_rows(CSV_DIR / "suitability_profiles.csv", profile_rows)
    write_rows(CSV_DIR / "suitability_ecdf.csv", ecdf_rows)
    write_rows(CSV_DIR / "suitability_qq.csv", qq_rows)

    var_rows = []
    for key, var in suitability["variance"].items():
        flat = {"dimension": key}
        for field, value in var.items():
            if field.endswith("_ci") and isinstance(value, list):
                flat[f"{field}_lo"] = value[0]
                flat[f"{field}_hi"] = value[1]
            else:
                flat[field] = value
        var_rows.append(flat)
    write_rows(CSV_DIR / "suitability_variance.csv", var_rows)

    culling_rows = []
    for split in ("all", "test"):
        block = suitability["culling"][split]
        for key, metrics in block.items():
            flat = {"split": split, "dimension": key}
            for field, value in metrics.items():
                if field.endswith("_ci") and isinstance(value, list):
                    flat[f"{field}_lo"] = value[0]
                    flat[f"{field}_hi"] = value[1]
                else:
                    flat[field] = value
            culling_rows.append(flat)
    write_rows(CSV_DIR / "suitability_culling.csv", culling_rows)

    global_rows = []
    for split in ("all", "test"):
        block = suitability["global"][split]
        for key, metrics in block.items():
            flat = {"split": split, "dimension": key}
            for field, value in metrics.items():
                if field.endswith("_ci") and isinstance(value, list):
                    flat[f"{field}_lo"] = value[0]
                    flat[f"{field}_hi"] = value[1]
                else:
                    flat[field] = value
            global_rows.append(flat)
    write_rows(CSV_DIR / "suitability_global.csv", global_rows)

    grouped = suitability["pairwise_model"]["grouped_cv_dev"]
    write_rows(
        CSV_DIR / "suitability_pairwise_coefficients.csv",
        grouped.get("coefficients") or [],
    )
    holdout = suitability["pairwise_model"]["holdout"]
    write_rows(
        CSV_DIR / "suitability_pairwise_holdout.csv",
        [
            {"split": "grouped_cv_dev", **(grouped.get("cv") or {}), "pairs": grouped.get("pairs"), "equation": grouped.get("equation")},
            {"split": "test_uncalibrated", **(holdout.get("test_uncalibrated") or {}), "temperature": holdout.get("temperature")},
            {"split": "test_calibrated", **(holdout.get("test_calibrated") or {}), "temperature": holdout.get("temperature")},
        ],
    )
    qg = suitability["global"].get("candidate_q_global") or {}
    q_rows = [{"term": "intercept", "weight_std": qg.get("intercept"), "n": qg.get("n"), "cv_spearman": qg.get("cv_spearman"), "cv_mae": qg.get("cv_mae")}]
    for name, weight in (qg.get("weights_std") or {}).items():
        q_rows.append({"term": name, "weight_std": weight, "n": qg.get("n"), "cv_spearman": qg.get("cv_spearman"), "cv_mae": qg.get("cv_mae")})
    write_rows(CSV_DIR / "suitability_q_global.csv", q_rows)

    sub_rows = []
    for row in suitability.get("subgroups") or []:
        flat = {k: v for k, v in row.items() if not isinstance(v, dict)}
        for key, value in row.items():
            if isinstance(value, dict) and "acc" in value:
                flat[f"{key}_acc"] = value.get("acc")
                bounds = value.get("ci") or [None, None]
                flat[f"{key}_ci_lo"] = bounds[0]
                flat[f"{key}_ci_hi"] = bounds[1]
        sub_rows.append(flat)
    write_rows(CSV_DIR / "suitability_subgroups.csv", sub_rows)
    write_rows(
        CSV_DIR / "suitability_findings.csv",
        [{"n": i + 1, "finding": text} for i, text in enumerate(suitability.get("findings") or [])],
    )

    suit_corr = suitability["correlation"]
    write_rows(CSV_DIR / "suitability_pooled_vs_within.csv", suit_corr.get("pooled_vs_within") or [])
    pca = suitability.get("pca") or {}
    loadings = pca.get("loadings") or {}
    if loadings and isinstance(next(iter(loadings.values())), dict):
        pca_rows = []
        for component, weights in loadings.items():
            row = {"component": component}
            row.update(weights)
            pca_rows.append(row)
        write_rows(CSV_DIR / "suitability_pca_loadings.csv", pca_rows)
    elif loadings and isinstance(next(iter(loadings.values())), list):
        components = pca.get("explained") or []
        pca_rows = []
        for dim, weights in loadings.items():
            row = {"dimension": dim}
            for i, weight in enumerate(weights):
                row[f"pc{i + 1}"] = weight
            pca_rows.append(row)
        write_rows(CSV_DIR / "suitability_pca_loadings.csv", pca_rows)
        _ = components
    co = suitability.get("co_missingness") or {}
    if co.get("keys") and co.get("p_missing_given_row_missing"):
        write_square(
            CSV_DIR / "suitability_co_missingness.csv",
            co["keys"],
            co["p_missing_given_row_missing"],
        )

    write_summary(stats, matrix, regression, stacks, keywords, suitability)
    print(f"wrote {CSV_DIR} and SUMMARY.md")


def write_summary(stats, matrix, regression, stacks, keywords, suitability) -> None:
    keys = stats["keys"]
    meta = stats["meta"]
    desc = stats["descriptives"]
    generated = stats.get("generated_at") or suitability["manifest"].get("generated_at")
    image_count = stats["image_count"]

    coverage_rows = [
        [
            label(key),
            meta[key]["kind"],
            fmt(meta[key]["count"], 0),
            fmt(meta[key]["coverage_pct"], 2),
            fmt(desc[key]["mean"]),
            fmt(desc[key]["median"]),
            fmt(desc[key]["std"]),
            fmt(desc[key]["skewness"], 2),
            fmt(desc[key]["outliers"], 0),
        ]
        for key in keys
    ]

    spearman_pairs = pairs_from_square(keys, stats["correlation"]["spearman"])
    pair_rows = [
        [label(a), label(b), fmt(r)]
        for a, b, r in spearman_pairs[:8]
    ]
    weak_rows = [
        [label(a), label(b), fmt(r)]
        for a, b, r in sorted(spearman_pairs, key=lambda item: abs(item[2]))[:5]
    ]

    coef_rows = []
    for coef in regression["coefficients"]:
        coef_rows.append(
            [
                label(coef["name"]),
                fmt(coef["beta"]),
                fmt(coef["std_beta"]),
                fmt(coef["configured_weight"]),
                fmt(coef["vif"], 2),
                fmt(coef["p"], 4) if coef["p"] not in (0, 0.0) else "<0.0001",
            ]
        )

    stack_by_auc = sorted(stacks["models"], key=lambda row: (row["pick_auc"] is None, -(row["pick_auc"] or 0)))
    stack_rows = [
        [
            label(row["dimension"]),
            fmt(row["pick_auc"]),
            fmt(row["reject_auc"]),
            fmt(row["pick_top1_rate"]),
            fmt(row["best_match_rate"]),
            fmt(row["within_share"]),
            fmt(row["tie_rate"]),
            fmt(row["stacks"], 0),
        ]
        for row in stack_by_auc
    ]

    shifts = []
    for entry in keywords["keywords"]:
        for dim in entry["dimensions"]:
            d = dim.get("cohens_d")
            if d is None:
                continue
            shifts.append((abs(d), entry["keyword"], entry["images"], dim["dimension"], d, dim.get("mean_delta")))
    shifts.sort(reverse=True)
    shift_rows = [
        [kw, fmt(images, 0), label(dim), fmt(d), fmt(delta)]
        for _, kw, images, dim, d, delta in shifts[:12]
    ]

    suit_rows = []
    for row in suitability["suitability"]["map"]:
        suit_rows.append(
            [
                label(row["dimension"]),
                row["role"],
                fmt(row["G"]),
                ci(row.get("G_ci")),
                fmt(row["C"]),
                ci(row.get("C_ci")),
                "yes" if row.get("provisional") else "no",
            ]
        )

    flips = [row for row in suitability["correlation"]["pooled_vs_within"] if row.get("sign_flip")]
    biggest_delta = sorted(
        suitability["correlation"]["pooled_vs_within"],
        key=lambda row: abs(row["delta"]),
        reverse=True,
    )[:6]
    delta_rows = [
        [label(row["a"]), label(row["b"]), fmt(row["pooled"]), fmt(row["within"]), fmt(row["delta"]), "yes" if row["sign_flip"] else "no"]
        for row in biggest_delta
    ]

    labels = suitability["labels"]
    clusters = suitability["clusters"]
    split = suitability["split"]["images"]
    thresholds = suitability["suitability"]["thresholds"]
    findings = suitability.get("findings") or []
    recs = regression.get("recommendations") or []
    qg = suitability["global"].get("candidate_q_global") or {}
    holdout = suitability["pairwise_model"]["holdout"]
    cv = suitability["pairwise_model"]["grouped_cv_dev"].get("cv") or {}

    # Decile means of each model when ranked by general (the default curves view).
    decile_header = ["Decile"] + [label(key) for key in keys]
    decile_table_rows = []
    by_decile: dict[int, dict[str, float]] = {}
    # Recompute lightly from rank file logic already in memory via matrix
    series = matrix["series"]
    indexed = [(i, series["general"][i]) for i in range(len(matrix["image_ids"])) if series["general"][i] is not None]
    indexed.sort(key=lambda item: (item[1], item[0]))
    n = len(indexed)
    for decile in range(10):
        start = decile * n // 10
        end = (decile + 1) * n // 10
        chunk = indexed[start:end]
        means = {}
        for key in keys:
            vals = [series[key][i] for i, _ in chunk if series[key][i] is not None]
            means[key] = sum(vals) / len(vals) if vals else None
        by_decile[decile] = means
        decile_table_rows.append([str(decile + 1)] + [fmt(means[key]) for key in keys])

    lines = [
        "# Score analytics",
        "",
        f"Library snapshot behind `http://localhost:7860/ui/scores` (every tab, every dimension). "
        f"Fetched from `GET /api/analytics/scores/*` on {generated}. "
        f"Scope is the full library: **{image_count:,} images**, **{len(keys)} dimensions**. "
        f"Scores are normalized 0–1. No keyword layer was applied.",
        "",
        "Composites are `general`, `technical`, and `aesthetic`. "
        "The other six columns are model scores. "
        f"About {100 - meta['general']['coverage_pct']:.1f}% of images have no composite score.",
        "",
        "## Files",
        "",
        "CSV tables are in `csv/`. Raw JSON payloads sit next to this file.",
        "",
        "| File | Contents |",
        "| --- | --- |",
        "| `csv/scores_matrix.csv` | One row per image: `image_id` and all nine scores (rank-curve source) |",
        "| `csv/rank_curve_deciles.csv` | Mean of every dimension inside each decile, ranked by each dimension |",
        "| `csv/descriptives.csv` | Mean, median, quartiles, skew, kurtosis, whiskers, outlier counts |",
        "| `csv/histograms.csv` | 50-bin histograms on [0, 1] |",
        "| `csv/correlation_*.csv` | Pearson and Spearman r, p, and pairwise n |",
        "| `csv/regression_*.csv` | OLS of General on the six model scores, coefficients, residual sample |",
        "| `csv/stacks_*.csv` | Within-stack culling signal and agreement |",
        "| `csv/keywords.csv` | Top keywords × dimension, including Cohen's d vs the rest of the library |",
        "| `csv/suitability_*.csv` | Nₐ/Nᵦ map, profiles, variance, culling, global agreement, subgroups |",
        "",
        "## Distributions",
        "",
        md_table(
            ["Dimension", "Kind", "N", "Coverage %", "Mean", "Median", "SD", "Skew", "Outliers"],
            coverage_rows,
        ),
        "",
        "AVA sits low and tight (mean 0.412, SD 0.053). LIQE sits high (mean 0.755). "
        "ARNIQA and TOPIQ-NR are narrow and left-skewed (skew −1.52 and −1.86). "
        "General, Technical, and Aesthetic spread widely (SD about 0.18) and peak above their means.",
        "",
        "## Correlations",
        "",
        "Spearman, pairwise-complete. Strongest pairs:",
        "",
        md_table(["A", "B", "ρ"], pair_rows),
        "",
        "Weakest pairs:",
        "",
        md_table(["A", "B", "ρ"], weak_rows),
        "",
        "General tracks Technical (Spearman ρ 0.961; Pearson r 0.967) because Technical is a large part of the General fusion. "
        "AVA tracks Aesthetic (ρ 0.714) and is loosely tied to the other model scores (ρ 0.18–0.33).",
        "",
        "## Regression",
        "",
        f"Target **General**, predictors {', '.join(label(p) for p in regression['predictors'])}. "
        f"Complete rows **{regression['n']:,}** of {regression['image_count']:,}. "
        f"R² **{regression['r2']:.3f}**, adjusted R² **{regression['adj_r2']:.3f}**, "
        f"5-fold CV R² **{regression['cv_r2']:.3f}**, RMSE **{regression['rmse']:.3f}**, MAE **{regression['mae']:.3f}**.",
        "",
        "That R² is expected: General is a weighted fusion of LIQE, SPAQ, TOPIQ-NR, ARNIQA, and AVA. "
        "The regression is recovering that fusion, plus a small CLIP Quality term that is not in the configured weights. "
        "Standardized β ranks the predictors on a common scale; configured weight is the fusion weight.",
        "",
        md_table(["Predictor", "β", "Std β", "Configured weight", "VIF", "p"], coef_rows),
        "",
        f"Intercept β = {regression['intercept']['beta']:.3f}. Rank deficient: {regression['rank_deficient']}.",
        "",
        "Recommendations from the API:",
        "",
    ]
    for rec in recs:
        lines.append(f"- **{rec['severity']}.** {rec['message']}")
    lines += [
        "",
        "## Rank curves",
        "",
        "The curves tab sorts images by one dimension and plots the others in that order. "
        "`csv/scores_matrix.csv` is the unsorted source. "
        "Decile means below are images ranked by **General** (the page default). Decile 1 is the lowest General scores.",
        "",
        md_table(decile_header, decile_table_rows),
        "",
        "`csv/rank_curve_deciles.csv` repeats this for every ranking dimension.",
        "",
        "## Stacks (culling)",
        "",
        f"{stacks['stacks_considered']:,} stacks with at least {stacks['min_size']} scored images "
        f"({stacks['images_in_stacks']:,} images). "
        f"{stacks['stacks_with_picks']:,} of those stacks have a pick flag. "
        "Pick AUC is P(a picked image scores above a non-pick in the same stack). 0.5 is chance. "
        "`best_match_rate` is how often the stack's stored best image is the top score.",
        "",
        md_table(
            ["Dimension", "Pick AUC", "Reject AUC", "Top-1 pick", "Best-image match", "Within-stack var share", "Tie rate", "Stacks"],
            stack_rows,
        ),
        "",
        "API ranking by culling signal: " + ", ".join(label(k) for k in stacks["ranking"]) + ".",
        "",
        "General leads pick separation (AUC 0.815), then Technical (0.777) and Aesthetic (0.758). "
        "CLIP Quality is the weakest (AUC 0.597), then ARNIQA (0.631). "
        "Within-stack variance is a small share for every dimension (6.5–10.4%); CLIP Quality and ARNIQA have the largest share. "
        "General matches the stored best image in 95.8% of stacks.",
        "",
        "## Keyword layers",
        "",
        f"Top {len(keywords['keywords'])} keywords with at least 30 images. "
        "Cohen's d compares images with the keyword to the rest of the library. "
        f"The library is dominated by a few tags (wildlife alone is {keywords['keywords'][0]['images']:,} images), so most shifts are small.",
        "",
        "Largest absolute Cohen's d:",
        "",
        md_table(["Keyword", "Images", "Dimension", "Cohen's d", "Mean delta"], shift_rows),
        "",
        "Full grid: `csv/keywords.csv`.",
        "",
        "## Suitability (Nₐ / Nᵦ)",
        "",
        f"Clusters: **{clusters['count']:,}** stacks ({clusters['images_in_clusters']:,} images) and "
        f"**{clusters['standalone_images']:,}** standalone images. "
        f"Split by cluster hash: train {split['train']:,}, validation {split['validation']:,}, test {split['test']:,}. "
        "The map below is the untouched test split.",
        "",
        f"Culling labels: `{labels['culling_source']}` (independent: {str(labels['culling_independent']).lower()}). "
        f"Global labels: `{labels['global_source']}` (independent: {str(labels['global_independent']).lower()}). "
        "Both are provisional.",
        "",
        "Thresholds:",
        "",
        f"- Nₐ (global): {thresholds['global']}",
        f"- Nᵦ (culling): {thresholds['culling']}",
        "",
        md_table(
            ["Dimension", "Role", "G", "G 95% CI", "C", "C 95% CI", "Provisional"],
            suit_rows,
        ),
        "",
        "G is burst-weighted Spearman of the score against the global rating on the test split. "
        "C is macro pairwise accuracy inside clusters. "
        "A model is in Nₐ when the lower end of the G interval clears 0.3, and in Nᵦ when the lower end of C clears 0.6.",
        "",
        "Roles split, and every row is provisional because the labels are unverified. "
        "General, Technical, Aesthetic, LIQE, and SPAQ are in both Nₐ and Nᵦ. "
        "ARNIQA, CLIP Quality, and TOPIQ-NR are in Nₐ only: their culling intervals stay under 0.6. "
        "AVA is in Nᵦ only: its culling interval clears 0.6, and its global interval starts at 0.283. "
        "Among the model scores, LIQE has the strongest global agreement (G 0.557) and the strongest culling accuracy (C 0.731).",
        "",
        f"Pairwise logistic model (grouped CV): accuracy {cv.get('accuracy', float('nan')):.3f}, "
        f"log loss {cv.get('log_loss', float('nan')):.3f}, ECE {cv.get('ece', float('nan')):.3f}. "
        f"Holdout test accuracy {holdout['test_calibrated']['accuracy']:.3f} "
        f"(temperature {holdout.get('temperature'):.3f}).",
        "",
        f"Candidate Q_global (ridge on standardized model scores, grouped CV Spearman {qg.get('cv_spearman'):.3f}, "
        f"MAE {qg.get('cv_mae'):.3f}, n {qg.get('n'):,}). Weights are in `csv/suitability_q_global.csv`.",
        "",
        "Largest pooled-vs-within Spearman gaps (a positive within correlation that shrinks inside a stack means the models agree across the library more than they agree on near-duplicates):",
        "",
        md_table(["A", "B", "Pooled ρ", "Within ρ", "Delta", "Sign flip"], delta_rows),
        "",
        f"Sign flips: {len(flips)}.",
        "",
        "API findings:",
        "",
    ]
    for text in findings:
        lines.append(f"- {text}")
    notes = labels.get("notes") or []
    if notes:
        lines += ["", "Label notes:", ""]
        for text in notes:
            lines.append(f"- {text}")
    lines.append("")
    (ROOT / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
