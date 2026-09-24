---
type: Planning Spec
title: Everypixel UGC correlation study
description: Phase 1 read-only harness to compare Everypixel UGC quality with local IQA composites and registry models.
resource: docs/planning/integrations/EVERYPIXEL_CORRELATION_STUDY.md
tags:
  - everypixel
  - scoring
  - research
timestamp: 2026-09-24T00:00:00Z
okf_version: 0.1
---

# Everypixel UGC correlation study

**Tracking:** [GitHub #392](https://github.com/synthet/image-scoring-backend/issues/392)

## Objective

Measure alignment between **Everypixel UGC** outputs (**`quality.class` 1–5** primary, **`quality.score` 0–1** secondary) and existing Vexlum signals (`score_general`, `score_technical`, `score_aesthetic`, plus `image_model_scores` for LIQE, SPAQ, AVA, TOPIQ, ARNIQA).

No production writes in phase 1 — artifacts live under `reports/everypixel-correlation/`.

## Phase 1 harness (implemented)

| Step | Script | Output |
|------|--------|--------|
| 1. Cohort | `scripts/research/everypixel_correlation/export_cohort.py` | `reports/everypixel-correlation/manifest.json` |
| 2. UGC API | `scripts/research/everypixel_correlation/fetch_ugc.py` | `everypixel_ugc.jsonl` |
| 3. Analysis | `scripts/research/everypixel_correlation/join_and_analyze.py` | `correlation_matrix.csv`, `correlation_summary.md` |

### Acceptance criteria (#392)

- [x] `export_cohort.py` → reproducible manifest under `reports/everypixel-correlation/`
- [x] `fetch_ugc.py` → `/v1/quality_ugc` with spend guard (400 calls, `estimated_cost_usd` 0 under trial assumptions)
- [x] `join_and_analyze.py` → `correlation_matrix.csv` + `correlation_summary.md`
- [x] This planning note

Run in **gpu-shell** (DB + RAW decode + `.env` credentials):

```powershell
scripts\batch\docker_gpu_run.bat scripts/research/everypixel_correlation/export_cohort.py --require-file --per-quintile 80
scripts\batch\docker_gpu_run.bat scripts/research/everypixel_correlation/fetch_ugc.py
scripts\batch\docker_gpu_run.bat scripts/research/everypixel_correlation/join_and_analyze.py
```

Pilot: `--per-quintile 5` or `fetch_ugc.py --limit N`.

## Statistical protocol

Phase 1 analysis follows the multivariate scoring-dimension workflow (descriptives →
correlation → VIF → OLS → evaluation), as summarized in external note
*Statistical Modeling of Scoring Dimensions* (`deep-research-report (2).md`).

Implemented in `statistical_modeling.py`, invoked from `join_and_analyze.py`:

| Step | Output |
|------|--------|
| Descriptive stats (mean, quartiles, skew) | `descriptive_stats.csv` |
| Pairwise Pearson + Spearman among predictors | `predictor_correlation_pairs.csv` |
| VIF multicollinearity (local IQA + composites) | `vif_predictors.csv` |
| OLS: `ugc_score` ~ local dimensions | `regression_models.json` |
| OLS: `ugc_class` ~ local (exploratory) | same JSON |
| Incremental R²: `score_general` ~ liqe+topiq vs +`ugc_score` | same JSON |
| Narrative | `modeling_summary.md` |

**Primary inferential target for Everypixel remains Spearman** on `ugc_class` (ordinal).
OLS on class is screening only; use VIF before interpreting individual β coefficients.

## Phase 1 results (2026-09-24)

**Cohort:** manifest `38ef7109cece4116`, **400** images (80 per `score_general` quintile, seed 42), all NEF with on-disk paths. **UGC fetch:** 400/400 OK (embedded JPEG preview → Everypixel). **Join:** 400 rows.

Spearman ρ (primary **`ugc_class`**, n=400):

| feature | ρ | p (approx) |
|---------|---:|---|
| ava | **0.38** | <0.001 |
| score_general | 0.28 | <0.001 |
| liqe | 0.27 | <0.001 |
| score_aesthetic | 0.26 | <0.001 |
| topiq | 0.26 | <0.001 |
| rating | 0.25 | <0.001 |
| score_technical | 0.24 | <0.001 |
| arniqa | 0.17 | <0.001 |
| spaq | **0.08** | ~0.13 (n.s.) |

**`ugc_score`** ranks similarly (strongest: AVA ~0.39, general ~0.28; SPAQ again weak ~0.08).

**Interpretation (phase 1 only):**

- UGC class aligns **moderately** with Vexlum **general** and composites, not redundant with LIQE alone.
- **AVA** tracks UGC class **more** than LIQE/TOPIQ in this sample — worth checking genre mix (many wedding/portrait NEFs).
- **SPAQ** is largely **orthogonal** to Everypixel UGC here — fusion would not duplicate SPAQ signal.
- Rendition confound: local scores used full pipeline history; Everypixel saw **embedded JPEG previews** (~same as smoke test `raw_preview`).

Artifacts (local, under `reports/everypixel-correlation/`): `manifest.json`, `everypixel_ugc.jsonl`, `everypixel_usage.json`, `correlation_matrix.csv`, `correlation_summary.md`.

**Recommendation:** Do **not** promote to fusion yet. Next (outside #392): quintile-stratified ρ, user-label subset, disagreement mining, optional **shadow** registry row `everypixel_ugc`.

## Later phases (not in #392)

- Main sample (n≈2,000), disagreement mining, optional shadow registry model.

## References

- [EVERYPIXEL.md](../../integrations/EVERYPIXEL.md)
- [WEIGHTED_SCORING_STRATEGY.md](../../technical/WEIGHTED_SCORING_STRATEGY.md)
