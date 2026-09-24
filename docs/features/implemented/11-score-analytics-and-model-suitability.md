---
type: Implemented Feature
title: Score analytics and model suitability
description: /ui/scores dashboard, /api/analytics/scores/* endpoints and export scripts for comparing every scoring dimension globally, per keyword and inside stacks, including the Nₐ / Nᵦ model-suitability toolkit.
resource: docs/features/implemented/11-score-analytics-and-model-suitability.md
tags: [features, scoring, analytics, culling, statistics, frontend]
timestamp: 2026-09-24T00:00:00Z
okf_version: 0.1
---

# Score analytics and model suitability

Read-only tooling to compare every score dimension (composites, production models, shadow models) and decide which models suit **global quality (Nₐ)** versus **intra-cluster culling (Nᵦ)**.

**Code:** [`modules/score_analytics/`](../../../modules/score_analytics/) · router [`modules/api/routers/score_analytics.py`](../../../modules/api/routers/score_analytics.py) · SPA [`frontend/src/features/score-analytics/`](../../../frontend/src/features/score-analytics/) · issue [#393](https://github.com/synthet/image-scoring-backend/issues/393)

## Data

- One row per image: `images.score_{general,technical,aesthetic}` plus every `image_model_scores.model_name` with `status = 'success'`, read as `COALESCE(normalized, raw_score)` (shadow models included and marked).
- Stack layer: `images.stack_id`, `images.pick_status`, `stacks.best_image_id`. Keyword layer: `image_keywords` ⋈ `keywords_dim.keyword_norm` (exact, lower-cased).
- The matrix and derived results are cached in-process and rebuilt when a DB fingerprint changes (counts, max timestamps, exact `numeric` score sums, id-weighted pick / stack / keyword sums; re-checked at most every 10 s). The matrix endpoint serves gzipped JSON with an `ETag` (`If-None-Match` → 304).

## Dashboard (`/ui/scores`)

| Tab | Content |
|---|---|
| Rank curves | Pick a dimension; X = all images sorted by it (rising curve), Y = score; every other dimension plotted at the same X as points + rolling-mean trend. **A/B renderer toggle** (A = uPlot, B = ECharts) with first/last render timings. |
| Distributions | 50-bin histogram per dimension, boxplots, descriptives (mean, median, mode, SD, variance, IQR, skewness, kurtosis, outliers). |
| Correlations | Pearson / Spearman heatmap with p and n; highly correlated pairs (\|r\| ≥ 0.8). |
| Regression | OLS of a target on selectable predictors: β, standardized β, SE, t, p, CI, VIF, R², adj. R², 5-fold CV R², RMSE, MAE, F; residual plots; rule-based recommendations. |
| Stacks (culling) | Per dimension: within-stack spread, within-stack variance share, tie rate, top gap, pick / reject AUC, top-1 pick and best-image match; within-stack Spearman agreement. |
| Suitability Nₐ/Nᵦ | Label provenance audit, Uⱼ = (Gⱼ, Cⱼ) map with CIs, membership, culling metrics, variance decomposition, pairwise logistic model, pooled vs within-cluster correlation, subgroups. |
| Keyword layers | Cohen's d per keyword × dimension vs the rest of the library; click to scope the dashboard to a keyword. |

Every tab except Keyword layers accepts the **layer** (all images or one keyword).

Measured on a synthetic 50k-image / 8k-stack PostgreSQL seed (headless Chromium): uPlot drew ~50k line + ~407k scatter points in 265 ms (315 ms re-render) vs 1249 ms (1328 ms) for ECharts; `/stacks` 0.3 s, `/suitability` 9.5 s cold / 0.15 s cached.

## API (`/api/analytics/scores/*`, PostgreSQL only)

See [API_CONTRACT.md](../../technical/API_CONTRACT.md#score-analytics-endpoints): `matrix`, `stats`, `regression`, `stacks`, `keywords`, `suitability`.

## Model suitability method

Implements the research canvas *Vexlum Scoring — Global vs. Intra-Cluster Model Suitability*:

- **Label provenance / leakage guard** (`labels.py`): `culling_picks` with `auto_suggested = 0` are the only labels treated as independent. Auto-cull picks (`images.cull_policy_version` set), `culling_picks.auto_suggested = 1` and `images.rating` (derived from `score_general`) are never evidence. `image_xmp` ratings / picks are *unverified* (the app also writes XMP) and are flagged when they mirror the score-derived rating.
- **Variance distinction:** Var(s) = Var(E[s|C]) + E[Var(s|C)], image- and cluster-weighted, ICC(1), cluster-bootstrap CIs.
- **Correlation structure:** pooled vs within-cluster-centered Pearson / Spearman, Kendall τ-b, partial, distance correlation, Benjamini–Hochberg p-values, PCA; Simpson-type sign flips are listed.
- **Culling (Cⱼ):** within-cluster pairs graded pick = 2 > keep = 1 > reject = 0, each cluster weighted equally; macro pairwise accuracy, top-1, NDCG@1/3, τ-b with Poisson cluster-bootstrap CIs.
- **Cluster-relative model:** P(a ≻ b) = σ(Σⱼ βⱼ Δⱼ(a,b)) without intercept (reversal-symmetric); grouped CV by cluster, drop-one ablation, train / validation (temperature calibration) / untouched test split by cluster id hash; log loss, Brier, ECE.
- **Global (Gⱼ):** burst-downweighted Spearman with an independent global label; candidate ridge Q_global with grouped CV.
- **Membership:** Nₐ / Nᵦ from lower 95% CI bounds vs prespecified thresholds (defaults 0.3 Spearman, 0.6 pairwise accuracy); models can be in both or neither; composites are reported but never independent; results are marked *provisional* whenever labels are not verified independent.
- **Subgroups:** stack size, top keywords, camera (`image_exif.make/model`).
- **Not measurable today:** cross-run rescoring stability (one row per image × model) and cluster type (burst / eye focus / …) — reported explicitly.

Pick / Keep / Reject probabilities and deletion policy are out of scope until an independent human-labelled cohort exists; existing culling safeguards are unchanged.

## Scripts

| Script | Output |
|---|---|
| [`scripts/analysis/export_score_analytics.py`](../../../scripts/analysis/export_score_analytics.py) | Per layer (library + keywords): per-image scores, descriptives, histograms, correlations, regression, stack signals, per-stack rows; keyword profiles; `summary.json`. |
| [`scripts/analysis/model_suitability_report.py`](../../../scripts/analysis/model_suitability_report.py) | Manifest (fingerprint, query / code hashes, git SHA, versions), data dictionary, label audit, profiles / percentiles / ECDF-QQ, variance decomposition, correlation matrices, culling metrics (all / test), pairwise model, global metrics, suitability map, subgroups, `REPORT.md`. |

Run both in gpu-shell (see [AGENTS.md](../../../AGENTS.md)); neither writes to the database.
