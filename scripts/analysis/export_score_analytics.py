#!/usr/bin/env python3
"""Export score-dimension statistics from PostgreSQL to CSV / JSON files.

Computes, per *layer* (full library, then each selected keyword):

* descriptives per dimension (mean, median, mode, quartiles, IQR, variance, std,
  skewness, kurtosis, boxplot whiskers, outliers, 50-bin histogram)
* pairwise Pearson / Spearman correlation with p-values and n
* OLS regression of ``--target`` on the model scores (β, standardized β, SE, t,
  p, CI, VIF, R², adj. R², CV R², RMSE, MAE, F) and recommendations
* within-stack culling signals per dimension (spread, within-stack variance
  share, tie rate, top gap, pick / reject AUC, top-1 pick rate, best-image
  match rate) plus within-stack Spearman agreement and per-stack rows

plus per-keyword profiles vs the rest of the library and a ``summary.json``
manifest. Same code path as ``/api/analytics/scores/*``.

Run in gpu-shell (see AGENTS.md)::

    python scripts/analysis/export_score_analytics.py
    python scripts/analysis/export_score_analytics.py --keywords bird,sunset --top-keywords 0
    python scripts/analysis/export_score_analytics.py --out reports/score_analytics/run1 --formats csv
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from modules.score_analytics import data, service  # noqa: E402
from modules.score_analytics.io import Writer, _json_default  # noqa: E402

logger = logging.getLogger("export_score_analytics")

DESCRIPTIVE_FIELDS = [
    "count", "coverage_pct", "mean", "median", "mode", "min", "max", "range", "q1", "q3", "iqr",
    "variance", "std", "skewness", "kurtosis", "whisker_lo", "whisker_hi", "outliers",
]


def layer_slug(keyword: str | None) -> str:
    if keyword is None:
        return "library"
    return "keyword=" + (re.sub(r"[^a-z0-9._-]+", "_", keyword.lower()).strip("_") or "blank")


def export_layer(
    m: data.ScoreMatrix,
    w: Writer,
    slug: str,
    *,
    target: str,
    predictors: list[str] | None,
    min_stack_size: int,
    per_image: bool,
    per_stack: bool,
    file_paths: dict[int, str] | None = None,
) -> dict[str, Any]:
    """Write every characteristic for one layer; returns its summary entry."""
    base = f"layers/{slug}"
    summary: dict[str, Any] = {"scope": m.scope, "images": m.image_count, "dimensions": m.keys}
    if m.image_count == 0 or not m.keys:
        summary["skipped"] = "no scored images"
        return summary

    if per_image:
        rows = []
        for i, iid in enumerate(m.image_ids.tolist()):
            row = {
                "image_id": iid,
                "file_path": (file_paths or {}).get(iid),
                "stack_id": int(m.stack_ids[i]) or None,
                "pick_status": int(m.pick_status[i]),
            }
            for k in m.keys:
                v = m.series[k][i]
                row[k] = None if np.isnan(v) else round(float(v), 6)
            rows.append(row)
        w.csv(f"{base}/per_image_scores.csv", rows, ["image_id", "file_path", "stack_id", "pick_status", *m.keys])

    st = service.compute_stats(m)
    desc_rows = [{"dimension": k, "kind": m.meta[k]["kind"], **st["descriptives"][k]} for k in m.keys]
    w.csv(f"{base}/descriptives.csv", desc_rows, ["dimension", "kind", *DESCRIPTIVE_FIELDS])
    hist_rows = []
    for k in m.keys:
        h = st["descriptives"][k]["histogram"]
        width = (h["hi"] - h["lo"]) / len(h["counts"])
        for b, c in enumerate(h["counts"]):
            hist_rows.append({"dimension": k, "bin": b, "lo": h["lo"] + b * width, "hi": h["lo"] + (b + 1) * width, "count": c})
    w.csv(f"{base}/histograms.csv", hist_rows, ["dimension", "bin", "lo", "hi", "count"])

    corr = st["correlation"]
    long_rows = []
    for i, a in enumerate(m.keys):
        for j in range(i + 1, len(m.keys)):
            long_rows.append(
                {
                    "a": a,
                    "b": m.keys[j],
                    "n": corr["n"][i][j],
                    "pearson": corr["pearson"][i][j],
                    "pearson_p": corr["pearson_p"][i][j],
                    "spearman": corr["spearman"][i][j],
                    "spearman_p": corr["spearman_p"][i][j],
                }
            )
    w.csv(f"{base}/correlations_long.csv", long_rows, ["a", "b", "n", "pearson", "pearson_p", "spearman", "spearman_p"])
    w.matrix_csv(f"{base}/correlation_pearson.csv", m.keys, corr["pearson"])
    w.matrix_csv(f"{base}/correlation_spearman.csv", m.keys, corr["spearman"])
    w.json(f"{base}/stats.json", st)
    summary["skewed"] = [r["dimension"] for r in desc_rows if r.get("skewness") is not None and abs(r["skewness"]) > 1]

    try:
        preds = service.resolve_regression_inputs(m, target, predictors)
        reg = service.compute_regression(m, target, preds)
        w.json(f"{base}/regression.json", reg)
        w.csv(
            f"{base}/regression_coefficients.csv",
            reg["coefficients"],
            ["name", "beta", "std_beta", "se", "t", "p", "ci_lo", "ci_hi", "vif", "configured_weight"],
        )
        w.csv(f"{base}/regression_recommendations.csv", reg["recommendations"], ["severity", "message"])
        summary["regression"] = {
            k: reg[k] for k in ("target", "predictors", "complete_rows", "r2", "adj_r2", "cv_r2", "rmse", "mae", "f_stat", "f_p")
        }
    except service.ScoreAnalyticsInputError as e:
        summary["regression"] = {"skipped": str(e)}

    stk = service.compute_stacks(m, min_stack_size, per_stack=per_stack)
    w.csv(f"{base}/stacks_model_signals.csv", stk["models"])
    w.matrix_csv(f"{base}/stacks_agreement_spearman.csv", stk["keys"], stk["agreement"]["spearman"])
    if per_stack:
        w.csv(f"{base}/stacks_per_stack.csv", stk.pop("per_stack"))
    w.json(f"{base}/stacks.json", stk)
    summary["stacks"] = {
        k: stk[k] for k in ("stacks_considered", "images_in_stacks", "stacks_with_picks", "ranking")
    }
    return summary


def export_all(
    m: data.ScoreMatrix,
    out: Path,
    *,
    keywords: list[tuple[str, int | None]],
    keyword_ids: dict[str, np.ndarray],
    formats: set[str],
    target: str,
    predictors: list[str] | None,
    min_stack_size: int,
    per_image: bool,
    per_stack: bool,
    file_paths: dict[int, str] | None = None,
) -> dict[str, Any]:
    w = Writer(out, formats)
    layers: dict[str, Any] = {}
    opts = dict(target=target, predictors=predictors, min_stack_size=min_stack_size)
    logger.info("layer library: %d images", m.image_count)
    layers["library"] = export_layer(m, w, "library", per_image=per_image, per_stack=per_stack, file_paths=file_paths, **opts)

    profile_rows = []
    for kw, _count in keywords:
        layer = data.scope_matrix(m, kw, keyword_ids.get(kw, np.array([], dtype=np.int64)))
        slug = layer_slug(kw)
        logger.info("layer %s: %d images", slug, layer.image_count)
        layers[slug] = export_layer(layer, w, slug, per_image=False, per_stack=False, **opts)
        for row in service.keyword_profile(m, layer):
            profile_rows.append({"keyword": kw, "images": layer.image_count, **row})
    if profile_rows:
        w.csv("keyword_profiles.csv", profile_rows)
        w.json("keyword_profiles.json", profile_rows)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": m.fingerprint,
        "image_count": m.image_count,
        "dimensions": {k: m.meta[k] for k in m.keys},
        "options": {**opts, "formats": sorted(formats), "per_image": per_image, "per_stack": per_stack},
        "layers": layers,
        "files": sorted(set(w.files)) + ["summary.json"],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=_json_default), encoding="utf-8")
    return summary


def _load_file_paths() -> dict[int, str]:
    return {int(r[0]): r[1] for r in data._select("SELECT id, file_path FROM images")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, help="Output directory (default reports/score_analytics/<UTC stamp>)")
    ap.add_argument("--keywords", default="", help="Comma-separated keywords to export as layers")
    ap.add_argument("--top-keywords", type=int, default=20, help="Also export the N most frequent keywords (0 = none)")
    ap.add_argument("--min-keyword-images", type=int, default=30, help="Minimum images for --top-keywords")
    ap.add_argument("--target", default="general", help="Regression target dimension")
    ap.add_argument("--predictors", default="", help="Comma-separated predictors (default: all non-shadow models)")
    ap.add_argument("--min-stack-size", type=int, default=2)
    ap.add_argument("--formats", default="csv,json", help="csv, json or both")
    ap.add_argument("--no-per-image", action="store_true", help="Skip the wide per-image score CSV")
    ap.add_argument("--no-per-stack", action="store_true", help="Skip per-stack × dimension rows")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    formats = {f.strip() for f in args.formats.split(",") if f.strip()}
    if not formats <= {"csv", "json"}:
        ap.error("--formats accepts csv and/or json")
    out = args.out or Path(project_root) / "reports" / "score_analytics" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    m = data.load_matrix()
    keywords: dict[str, int | None] = {}
    for kw in args.keywords.split(","):
        norm = data.normalize_keyword(kw)
        if norm:
            keywords[norm] = None
    if args.top_keywords > 0:
        for kw, n in data.top_keywords(args.top_keywords, args.min_keyword_images):
            keywords.setdefault(kw, n)
    keyword_ids = {kw: data.keyword_image_ids(kw) for kw in keywords}

    summary = export_all(
        m,
        out,
        keywords=list(keywords.items()),
        keyword_ids=keyword_ids,
        formats=formats,
        target=args.target,
        predictors=[p.strip() for p in args.predictors.split(",") if p.strip()] or None,
        min_stack_size=args.min_stack_size,
        per_image=not args.no_per_image,
        per_stack=not args.no_per_stack,
        file_paths=None if args.no_per_image else _load_file_paths(),
    )
    logger.info("wrote %d files to %s", len(summary["files"]), out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
