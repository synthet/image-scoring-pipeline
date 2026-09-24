# Everypixel UGC correlation summary

Generated: 2026-09-24T01:51:02.424513+00:00

- Manifest: `38ef7109cece4116` — **400** sampled (80 per `score_general` quintile, seed 42)
- Joined rows (UGC ok): **400**

## Primary target: `ugc_class` (Spearman vs local scores)

| feature | n | ρ | p |
|---------|---:|---:|---:|
| ava | 400 | 0.3812 | 0.0 |
| score_general | 400 | 0.2787 | 0.0 |
| liqe | 400 | 0.2726 | 0.0 |
| score_aesthetic | 400 | 0.2571 | 0.0 |
| topiq | 400 | 0.2568 | 0.0 |
| rating | 400 | 0.2544 | 0.0 |
| score_technical | 400 | 0.2438 | 1e-06 |
| arniqa | 400 | 0.171 | 0.000592 |

## Secondary: `ugc_score`

| feature | n | ρ | p |
|---------|---:|---:|---:|
| ava | 400 | 0.3909 | 0.0 |
| score_general | 400 | 0.2844 | 0.0 |
| liqe | 400 | 0.2768 | 0.0 |
| score_aesthetic | 400 | 0.2661 | 0.0 |
| rating | 400 | 0.2634 | 0.0 |
| score_technical | 400 | 0.2428 | 1e-06 |
| topiq | 400 | 0.2418 | 1e-06 |
| arniqa | 400 | 0.1773 | 0.000368 |

## Notes

- Read-only study; does not write to `image_model_scores`.
- Everypixel UGC calls use JPEG renditions (RAW decoded server-side).
- Full matrix: `correlation_matrix.csv` in this directory.
- Multivariate pass: `modeling_summary.md`, `descriptive_stats.csv`, `vif_predictors.csv`, `regression_models.json`.

