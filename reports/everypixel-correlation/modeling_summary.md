# Everypixel study — multivariate modeling summary

Protocol: descriptive stats → pairwise correlation → VIF → OLS regression (see study planning doc § Statistical protocol).

## Multicollinearity (VIF on local predictors)

| predictor | VIF | aux R² | flag |
|-----------|----:|-------:|------|
| score_general | 1326.6463 | 0.9992 | high |
| score_technical | 636.8075 | 0.9984 | high |
| score_aesthetic | 230.9156 | 0.9957 | high |
| liqe | 114.7521 | 0.9913 | high |
| spaq | 37.4366 | 0.9733 | high |
| ava | 30.5149 | 0.9672 | high |
| topiq | 22.961 | 0.9564 | high |
| arniqa | 16.5968 | 0.9397 | high |

Predictors with VIF > 10: **8**.

## OLS: predict `ugc_score` from local dimensions

- n=400, R²=0.2415, adj R²=0.2259, RMSE=0.146242

| term | β | p |
|------|---:|---:|
| score_general | 1.640063 | 0.268537 |
| score_technical | -1.204759 | 0.239046 |
| score_aesthetic | 0.071741 | 0.906946 |
| liqe | -0.397828 | 0.332543 |
| spaq | -0.662814 | 0.050875 |
| ava | 0.404823 | 0.613844 |
| topiq | 0.642449 | 0.137598 |
| arniqa | 0.777632 | 0.077775 |

## OLS: predict `ugc_class` from local dimensions (screening)

- n=400, R²=0.2361, adj R²=0.2204, RMSE=0.810439
- Treat as exploratory only (`ugc_class` is ordinal 1–5; Spearman remains primary).

## Incremental value for `score_general`

- Baseline (liqe, topiq): R²=0.8045
- + `ugc_score`: R²=0.8052, ΔR²=0.0007
- `ugc_score` coefficient p=0.244089 (holding liqe, topiq fixed)

## Feature adjustment hints (from modeling pass)

- Drop or regularize predictors with **VIF > 10** before trusting individual OLS coefficients.
- **SPAQ** was weak vs UGC in Spearman; check VIF vs **AVA/LIQE** before fusion decisions.
- Do not promote Everypixel to fusion on R² alone — rendition confound (embedded JPEG vs pipeline).

Artifacts: `descriptive_stats.csv`, `predictor_correlation_pairs.csv`, `vif_predictors.csv`, `regression_models.json`.

