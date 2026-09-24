#!/usr/bin/env python3
"""Global (Nₐ) vs intra-cluster (Nᵦ) model suitability report — read-only.

Implements the research canvas "Vexlum Scoring — Global vs. Intra-Cluster Model
Suitability" on the live PostgreSQL data:

* manifest (snapshot fingerprint, query / code hashes, git SHA, versions, grouping)
* data dictionary for every score dimension (status counts, raw / normalized
  ranges, versions, first / last scored) and label provenance audit
* extended per-dimension profiles, co-missingness, variance decomposition
* pooled vs within-cluster Pearson / Spearman, Kendall τ-b, partial and
  distance correlation (BH-adjusted), PCA
* within-cluster pairwise / top-1 / NDCG / τ-b culling metrics with
  cluster-bootstrap CIs, pairwise logistic ensemble (grouped CV, ablation,
  validation-set temperature calibration, untouched test)
* global agreement with independent labels and a candidate Q_global
* Uⱼ = (Gⱼ, Cⱼ) suitability map, subgroups (stack size / keyword / camera)

Nothing is written to the database. Run in gpu-shell (see AGENTS.md)::

    python scripts/analysis/model_suitability_report.py
    python scripts/analysis/model_suitability_report.py --culling-labels manual --bootstrap 500
    python scripts/analysis/model_suitability_report.py --keyword bird --out reports/suitability/bird
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from modules.score_analytics import data, labels, suitability_report  # noqa: E402
from modules.score_analytics.io import Writer  # noqa: E402

logger = logging.getLogger("model_suitability_report")

PROFILE_FIELDS = [
    "n", "missing_pct", "finite_pct", "min", "max", "below_bound", "above_bound", "mean", "median", "variance",
    "std", "mad", "iqr", "skewness", "excess_kurtosis", "bimodality_coefficient", "bimodal_hint", "unique",
    "tie_fraction", "floor_pct", "ceiling_pct", "near_bound_pct", "two_decimal_grid_pct", "entropy_norm",
]


def _git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return None


def _ci(v: Any) -> tuple[Any, Any]:
    return (v[0], v[1]) if isinstance(v, (list, tuple)) and len(v) == 2 else (None, None)


def write_report(report: dict[str, Any], man: dict[str, Any], dictionary: list[dict[str, Any]], out: Path, formats: set[str]) -> list[str]:
    w = Writer(out, formats)
    keys = report["dimensions"]
    w.json("manifest.json", man)
    w.json("report.json", {"manifest": man, "data_dictionary": dictionary, **report})
    w.csv("data_dictionary.csv", [{**d, "versions": ";".join(f"{v['version']}={v['rows']}" for v in d.get("versions", []))} for d in dictionary])
    w.json("label_audit.json", report["labels"])

    prof_rows = []
    pct_rows = []
    for k in keys:
        p = report["profiles"][k]
        lo, hi = _ci(p.get("mean_ci"))
        mlo, mhi = _ci(p.get("median_ci"))
        prof_rows.append({"dimension": k, "kind": report["kinds"][k], **{f: p.get(f) for f in PROFILE_FIELDS},
                          "mean_ci_lo": lo, "mean_ci_hi": hi, "median_ci_lo": mlo, "median_ci_hi": mhi})
        for q, v in (p.get("percentiles") or {}).items():
            pct_rows.append({"dimension": k, "percentile": q, "value": v})
    w.csv("profiles.csv", prof_rows, ["dimension", "kind", *PROFILE_FIELDS, "mean_ci_lo", "mean_ci_hi", "median_ci_lo", "median_ci_hi"])
    w.csv("percentiles.csv", pct_rows, ["dimension", "percentile", "value"])
    ecdf_rows = []
    for k in keys:
        p = report["profiles"][k]
        if "ecdf" in p:
            for prob, q, t in zip(p["ecdf"]["p"], p["ecdf"]["q"], p["qq_normal"]["theoretical"]):
                ecdf_rows.append({"dimension": k, "p": prob, "quantile": q, "normal_quantile": t})
    w.csv("ecdf_qq.csv", ecdf_rows, ["dimension", "p", "quantile", "normal_quantile"])
    w.matrix_csv("co_missingness.csv", keys, report["co_missingness"]["p_missing_given_row_missing"])

    var_rows = []
    for k in keys:
        v = report["variance"][k]
        var_rows.append({"dimension": k, **{f: v.get(f) for f in (
            "clusters", "images", "total_var", "between_var", "within_var", "within_share_image_weighted",
            "within_share_cluster_weighted", "icc1", "median_within_sd", "median_within_range")},
            "within_share_image_weighted_ci": v.get("within_share_image_weighted_ci"),
            "within_share_cluster_weighted_ci": v.get("within_share_cluster_weighted_ci")})
    w.csv("variance_decomposition.csv", var_rows)

    corr = report["correlation"]
    for name in ("pooled_pearson", "pooled_spearman", "pooled_kendall_tau_b", "within_pearson", "within_spearman"):
        w.matrix_csv(f"correlation/{name}.csv", keys, corr[name]["r"])
        w.matrix_csv(f"correlation/{name}_p_bh.csv", keys, corr[name]["p_bh"])
    w.matrix_csv("correlation/partial_pearson.csv", keys, corr["partial_pearson"]["r"])
    w.matrix_csv("correlation/distance_correlation.csv", keys, corr["distance_correlation"]["r"])
    w.csv("correlation/pooled_vs_within.csv", corr["pooled_vs_within"], ["a", "b", "pooled", "within", "delta", "sign_flip"])
    w.json("pca.json", report["pca"])

    fields = ["pairwise_accuracy_macro", "pairwise_accuracy_micro", "top1_agreement", "ndcg_at_1", "ndcg_at_3",
              "kendall_tau_b_mean", "score_tie_rate", "pairs", "decisive_pairs", "label_tie_pairs", "clusters", "topk_clusters"]
    for split in ("all", "test"):
        rows = []
        for k in keys:
            c = report["culling"][split].get(k, {})
            lo, hi = _ci(c.get("pairwise_accuracy_macro_ci"))
            rows.append({"dimension": k, **{f: c.get(f) for f in fields}, "pairwise_accuracy_ci_lo": lo, "pairwise_accuracy_ci_hi": hi})
        w.csv(f"culling_metrics_{split}.csv", rows, ["dimension", *fields, "pairwise_accuracy_ci_lo", "pairwise_accuracy_ci_hi"])
    w.json("pairwise_model.json", report["pairwise_model"])
    coefs = report["pairwise_model"].get("grouped_cv_dev", {}).get("coefficients", [])
    if coefs:
        w.csv("pairwise_model_coefficients.csv", coefs)

    for split in ("all", "test"):
        rows = []
        for k, g in report["global"].get(split, {}).items():
            lo, hi = _ci(g.get("spearman_weighted_ci"))
            rows.append({"dimension": k, **{f: g.get(f) for f in ("n", "clusters", "spearman_weighted", "spearman_unweighted", "spearman_unweighted_p")},
                         "ci_lo": lo, "ci_hi": hi})
        if rows:
            w.csv(f"global_metrics_{split}.csv", rows)
    w.json("candidate_q_global.json", report["global"].get("candidate_q_global", {}))

    smap = [{**r, "G_ci": r["G_ci"], "C_ci": r["C_ci"], "caveats": "; ".join(r["caveats"])} for r in report["suitability"]["map"]]
    w.csv("suitability_map.csv", smap)
    w.json("suitability_map.json", report["suitability"])
    sub_rows = []
    for s in report["subgroups"]:
        for k in keys:
            v = s.get(k)
            if isinstance(v, dict):
                lo, hi = _ci(v.get("ci"))
                sub_rows.append({"stratum": s["stratum"], "value": s["value"], "clusters": s["clusters"], "dimension": k,
                                 "pairwise_accuracy": v.get("acc"), "ci_lo": lo, "ci_hi": hi})
        if "note" in s:
            sub_rows.append({"stratum": s["stratum"], "value": s["value"], "clusters": s["clusters"], "dimension": "", "note": s["note"]})
    w.csv("subgroups.csv", sub_rows, ["stratum", "value", "clusters", "dimension", "pairwise_accuracy", "ci_lo", "ci_hi", "note"])

    out.mkdir(parents=True, exist_ok=True)
    (out / "REPORT.md").write_text(suitability_report.to_markdown(report, man), encoding="utf-8")
    return sorted(set(w.files)) + ["REPORT.md"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, help="Output directory (default reports/model_suitability/<UTC stamp>)")
    ap.add_argument("--keyword", help="Restrict to images tagged with this keyword")
    ap.add_argument("--culling-labels", default="auto", choices=labels.CULLING_POLICIES)
    ap.add_argument("--trust-xmp-ratings", action="store_true", help="Treat image_xmp.rating as independent global labels")
    ap.add_argument("--min-size", type=int, default=2, help="Minimum images per cluster (stack)")
    ap.add_argument("--bootstrap", type=int, default=500, help="Cluster-bootstrap resamples")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--global-min", type=float, default=suitability_report.DEFAULTS["global_min"])
    ap.add_argument("--culling-min", type=float, default=suitability_report.DEFAULTS["culling_min"])
    ap.add_argument("--test-frac", type=float, default=suitability_report.DEFAULTS["test_frac"])
    ap.add_argument("--val-frac", type=float, default=suitability_report.DEFAULTS["val_frac"])
    ap.add_argument("--top-keywords", type=int, default=5, help="Keyword strata for subgroup analysis")
    ap.add_argument("--formats", default="csv,json")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    formats = {f.strip() for f in args.formats.split(",") if f.strip()}
    out = args.out or Path(project_root) / "reports" / "model_suitability" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    full = data.load_matrix()
    kw = data.normalize_keyword(args.keyword)
    m = data.scope_matrix(full, kw)
    bundle = labels.assemble(m, labels.load_label_rows(), culling_policy=args.culling_labels, trust_xmp_ratings=args.trust_xmp_ratings)
    keyword_ids = {k: data.keyword_image_ids(k) for k, _ in data.top_keywords(args.top_keywords, 30)} if kw is None else {}
    opts = {
        "min_size": args.min_size, "bootstrap": args.bootstrap, "seed": args.seed, "global_min": args.global_min,
        "culling_min": args.culling_min, "test_frac": args.test_frac, "val_frac": args.val_frac, "top_keywords": args.top_keywords,
    }
    logger.info("building report: %d images, labels=%s", m.image_count, bundle.culling_source)
    report = suitability_report.build_report(m, bundle, keyword_ids=keyword_ids, **opts)
    man = suitability_report.manifest(
        m, {**opts, "culling_labels": args.culling_labels, "trust_xmp_ratings": args.trust_xmp_ratings}, git_sha=_git_sha()
    )
    files = write_report(report, man, labels.load_data_dictionary(), out, formats)
    logger.info("wrote %d files to %s", len(files), out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
