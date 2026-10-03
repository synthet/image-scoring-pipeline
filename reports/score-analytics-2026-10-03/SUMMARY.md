# Score analytics

Library snapshot behind `http://localhost:7860/ui/scores` (every tab, every dimension). Fetched from `GET /api/analytics/scores/*` on 2026-10-03T19:29:51.995341+00:00. Scope is the full library: **78,890 images**, **9 dimensions**. Scores are normalized 0–1. No keyword layer was applied.

Composites are `general`, `technical`, and `aesthetic`. The other six columns are model scores. About 2.0% of images have no composite score.

## Files

CSV tables are in `csv/`. Raw JSON payloads sit next to this file.

| File | Contents |
| --- | --- |
| `csv/scores_matrix.csv` | One row per image: `image_id` and all nine scores (rank-curve source) |
| `csv/rank_curve_deciles.csv` | Mean of every dimension inside each decile, ranked by each dimension |
| `csv/descriptives.csv` | Mean, median, quartiles, skew, kurtosis, whiskers, outlier counts |
| `csv/histograms.csv` | 50-bin histograms on [0, 1] |
| `csv/correlation_*.csv` | Pearson and Spearman r, p, and pairwise n |
| `csv/regression_*.csv` | OLS of General on the six model scores, coefficients, residual sample |
| `csv/stacks_*.csv` | Within-stack culling signal and agreement |
| `csv/keywords.csv` | Top keywords × dimension, including Cohen's d vs the rest of the library |
| `csv/suitability_*.csv` | Nₐ/Nᵦ map, profiles, variance, culling, global agreement, subgroups |

## Distributions

| Dimension | Kind | N | Coverage % | Mean | Median | SD | Skew | Outliers |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| General | composite | 77,331 | 98.02 | 0.634 | 0.652 | 0.181 | -0.63 | 1,288 |
| Technical | composite | 77,331 | 98.02 | 0.655 | 0.680 | 0.181 | -0.79 | 1,839 |
| Aesthetic | composite | 77,331 | 98.02 | 0.589 | 0.600 | 0.186 | -0.29 | 14 |
| ARNIQA | model | 77,333 | 98.03 | 0.649 | 0.659 | 0.064 | -1.52 | 2,933 |
| AVA | model | 77,333 | 98.03 | 0.412 | 0.410 | 0.053 | -0.05 | 1,264 |
| CLIP Quality | model | 77,294 | 97.98 | 0.510 | 0.512 | 0.128 | -0.11 | 358 |
| LIQE | model | 77,333 | 98.03 | 0.755 | 0.764 | 0.188 | -0.94 | 1,166 |
| SPAQ | model | 77,333 | 98.03 | 0.581 | 0.605 | 0.132 | -0.73 | 596 |
| TOPIQ-NR | model | 77,333 | 98.03 | 0.598 | 0.608 | 0.077 | -1.86 | 2,691 |

AVA sits low and tight (mean 0.412, SD 0.053). LIQE sits high (mean 0.755). ARNIQA and TOPIQ-NR are narrow and left-skewed (skew −1.52 and −1.86). General, Technical, and Aesthetic spread widely (SD about 0.18) and peak above their means.

## Correlations

Spearman, pairwise-complete. Strongest pairs:

| A | B | ρ |
| --- | --- | --- |
| General | Technical | 0.961 |
| Aesthetic | SPAQ | 0.872 |
| Technical | TOPIQ-NR | 0.843 |
| General | LIQE | 0.836 |
| General | Aesthetic | 0.834 |
| Technical | LIQE | 0.795 |
| Technical | ARNIQA | 0.760 |
| General | TOPIQ-NR | 0.744 |

Weakest pairs:

| A | B | ρ |
| --- | --- | --- |
| ARNIQA | AVA | 0.182 |
| AVA | TOPIQ-NR | 0.201 |
| AVA | CLIP Quality | 0.249 |
| AVA | LIQE | 0.256 |
| Technical | AVA | 0.315 |

General tracks Technical (Spearman ρ 0.961; Pearson r 0.967) because Technical is a large part of the General fusion. AVA tracks Aesthetic (ρ 0.714) and is loosely tied to the other model scores (ρ 0.18–0.33).

## Regression

Target **General**, predictors ARNIQA, AVA, CLIP Quality, LIQE, SPAQ, TOPIQ-NR. Complete rows **77,294** of 78,890. R² **0.969**, adjusted R² **0.969**, 5-fold CV R² **0.969**, RMSE **0.032**, MAE **0.018**.

That R² is expected: General is a weighted fusion of LIQE, SPAQ, TOPIQ-NR, ARNIQA, and AVA. The regression is recovering that fusion, plus a small CLIP Quality term that is not in the configured weights. Standardized β ranks the predictors on a common scale; configured weight is the fusion weight.

| Predictor | β | Std β | Configured weight | VIF | p |
| --- | --- | --- | --- | --- | --- |
| ARNIQA | 0.222 | 0.079 | 0.100 | 2.10 | <0.0001 |
| AVA | 0.407 | 0.119 | 0.120 | 1.21 | <0.0001 |
| CLIP Quality | 0.045 | 0.032 | — | 1.72 | <0.0001 |
| LIQE | 0.499 | 0.519 | 0.350 | 2.87 | <0.0001 |
| SPAQ | 0.579 | 0.423 | 0.300 | 1.52 | <0.0001 |
| TOPIQ-NR | 0.185 | 0.079 | 0.130 | 2.84 | <0.0001 |

Intercept β = -0.524. Rank deficient: False.

Recommendations from the API:

- **info.** arniqa is strongly skewed (skewness=-1.52); a log or rank transform may stabilise variance.
- **info.** topiq is strongly skewed (skewness=-1.86); a log or rank transform may stabilise variance.
- **ok.** No severe multicollinearity or overfitting detected for this predictor set.

## Rank curves

The curves tab sorts images by one dimension and plots the others in that order. `csv/scores_matrix.csv` is the unsorted source. Decile means below are images ranked by **General** (the page default). Decile 1 is the lowest General scores.

| Decile | General | Technical | Aesthetic | ARNIQA | AVA | CLIP Quality | LIQE | SPAQ | TOPIQ-NR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.272 | 0.288 | 0.295 | 0.550 | 0.371 | 0.368 | 0.415 | 0.371 | 0.456 |
| 2 | 0.447 | 0.476 | 0.419 | 0.609 | 0.388 | 0.426 | 0.609 | 0.476 | 0.551 |
| 3 | 0.526 | 0.559 | 0.486 | 0.631 | 0.393 | 0.457 | 0.666 | 0.526 | 0.576 |
| 4 | 0.582 | 0.614 | 0.536 | 0.643 | 0.399 | 0.476 | 0.710 | 0.560 | 0.592 |
| 5 | 0.629 | 0.658 | 0.576 | 0.653 | 0.405 | 0.494 | 0.752 | 0.583 | 0.604 |
| 6 | 0.674 | 0.701 | 0.612 | 0.663 | 0.411 | 0.517 | 0.793 | 0.604 | 0.616 |
| 7 | 0.718 | 0.738 | 0.655 | 0.670 | 0.419 | 0.539 | 0.833 | 0.628 | 0.624 |
| 8 | 0.767 | 0.781 | 0.702 | 0.677 | 0.426 | 0.563 | 0.873 | 0.657 | 0.636 |
| 9 | 0.825 | 0.832 | 0.760 | 0.689 | 0.439 | 0.597 | 0.922 | 0.686 | 0.649 |
| 10 | 0.899 | 0.899 | 0.846 | 0.707 | 0.465 | 0.658 | 0.973 | 0.720 | 0.672 |

`csv/rank_curve_deciles.csv` repeats this for every ranking dimension.

## Stacks (culling)

11,174 stacks with at least 2 scored images (66,308 images). 9,575 of those stacks have a pick flag. Pick AUC is P(a picked image scores above a non-pick in the same stack). 0.5 is chance. `best_match_rate` is how often the stack's stored best image is the top score.

| Dimension | Pick AUC | Reject AUC | Top-1 pick | Best-image match | Within-stack var share | Tie rate | Stacks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| General | 0.815 | 0.803 | 0.662 | 0.958 | 0.066 | 0.196 | 11,174 |
| Technical | 0.777 | 0.768 | 0.634 | 0.747 | 0.070 | 0.184 | 11,174 |
| Aesthetic | 0.758 | 0.744 | 0.615 | 0.693 | 0.074 | 0.152 | 11,174 |
| LIQE | 0.708 | 0.687 | 0.605 | 0.618 | 0.065 | 0.341 | 11,174 |
| SPAQ | 0.696 | 0.686 | 0.580 | 0.602 | 0.081 | 0.243 | 11,174 |
| TOPIQ-NR | 0.663 | 0.654 | 0.570 | 0.503 | 0.087 | 0.321 | 11,174 |
| AVA | 0.642 | 0.634 | 0.540 | 0.458 | 0.084 | 0.373 | 11,174 |
| ARNIQA | 0.631 | 0.619 | 0.524 | 0.450 | 0.099 | 0.350 | 11,174 |
| CLIP Quality | 0.597 | 0.607 | 0.542 | 0.394 | 0.104 | 0.167 | 11,174 |

API ranking by culling signal: General, Technical, Aesthetic, LIQE, SPAQ, TOPIQ-NR, AVA, ARNIQA, CLIP Quality.

General leads pick separation (AUC 0.815), then Technical (0.777) and Aesthetic (0.758). CLIP Quality is the weakest (AUC 0.597), then ARNIQA (0.631). Within-stack variance is a small share for every dimension (6.5–10.4%); CLIP Quality and ARNIQA have the largest share. General matches the stored best image in 95.8% of stacks.

## Keyword layers

Top 20 keywords with at least 30 images. Cohen's d compares images with the keyword to the rest of the library. The library is dominated by a few tags (wildlife alone is 51,281 images), so most shifts are small.

Largest absolute Cohen's d:

| Keyword | Images | Dimension | Cohen's d | Mean delta |
| --- | --- | --- | --- | --- |
| street | 5,245 | AVA | -0.746 | -0.039 |
| cityscape | 4,386 | AVA | -0.662 | -0.035 |
| minimal | 10,345 | CLIP Quality | -0.647 | -0.081 |
| architecture | 3,679 | AVA | -0.619 | -0.032 |
| abstract | 4,181 | General | -0.610 | -0.109 |
| abstract | 4,181 | LIQE | -0.585 | -0.109 |
| abstract | 4,181 | Technical | -0.578 | -0.104 |
| minimal | 10,345 | SPAQ | -0.529 | -0.069 |
| urban | 9,817 | AVA | -0.528 | -0.027 |
| minimal | 10,345 | Technical | -0.526 | -0.094 |
| abstract | 4,181 | TOPIQ-NR | -0.517 | -0.039 |
| macro | 7,820 | CLIP Quality | 0.512 | 0.065 |

Full grid: `csv/keywords.csv`.

## Suitability (Nₐ / Nᵦ)

Clusters: **11,174** stacks (66,308 images) and **12,582** standalone images. Split by cluster hash: train 47,342, validation 15,660, test 15,888. The map below is the untouched test split.

Culling labels: `pick_status_unverified` (independent: false). Global labels: `xmp_rating` (independent: false). Both are provisional.

Thresholds:

- Nₐ (global): lower 95% CI of burst-weighted Spearman(score, global label) ≥ 0.3
- Nᵦ (culling): lower 95% CI of macro pairwise accuracy within clusters ≥ 0.6

| Dimension | Role | G | G 95% CI | C | C 95% CI | Provisional |
| --- | --- | --- | --- | --- | --- | --- |
| General | both | 0.610 | 0.584–0.634 | 0.805 | 0.788–0.821 | yes |
| Technical | both | 0.546 | 0.521–0.571 | 0.714 | 0.698–0.734 | yes |
| Aesthetic | both | 0.547 | 0.518–0.572 | 0.780 | 0.764–0.800 | yes |
| ARNIQA | global | 0.376 | 0.347–0.398 | 0.547 | 0.527–0.563 | yes |
| AVA | culling | 0.315 | 0.283–0.348 | 0.655 | 0.637–0.672 | yes |
| CLIP Quality | global | 0.348 | 0.319–0.376 | 0.547 | 0.529–0.566 | yes |
| LIQE | both | 0.557 | 0.532–0.582 | 0.731 | 0.709–0.749 | yes |
| SPAQ | both | 0.437 | 0.410–0.463 | 0.678 | 0.660–0.700 | yes |
| TOPIQ-NR | global | 0.416 | 0.389–0.442 | 0.599 | 0.582–0.619 | yes |

G is burst-weighted Spearman of the score against the global rating on the test split. C is macro pairwise accuracy inside clusters. A model is in Nₐ when the lower end of the G interval clears 0.3, and in Nᵦ when the lower end of C clears 0.6.

Roles split, and every row is provisional because the labels are unverified. General, Technical, Aesthetic, LIQE, and SPAQ are in both Nₐ and Nᵦ. ARNIQA, CLIP Quality, and TOPIQ-NR are in Nₐ only: their culling intervals stay under 0.6. AVA is in Nᵦ only: its culling interval clears 0.6, and its global interval starts at 0.283. Among the model scores, LIQE has the strongest global agreement (G 0.557) and the strongest culling accuracy (C 0.731).

Pairwise logistic model (grouped CV): accuracy 0.855, log loss 0.463, ECE 0.115. Holdout test accuracy 0.858 (temperature 1.080).

Candidate Q_global (ridge on standardized model scores, grouped CV Spearman 0.681, MAE 0.511, n 64,174). Weights are in `csv/suitability_q_global.csv`.

Largest pooled-vs-within Spearman gaps (a positive within correlation that shrinks inside a stack means the models agree across the library more than they agree on near-duplicates):

| A | B | Pooled ρ | Within ρ | Delta | Sign flip |
| --- | --- | --- | --- | --- | --- |
| General | CLIP Quality | 0.616 | 0.184 | -0.432 | no |
| Technical | CLIP Quality | 0.595 | 0.164 | -0.431 | no |
| ARNIQA | LIQE | 0.587 | 0.162 | -0.426 | no |
| CLIP Quality | LIQE | 0.618 | 0.199 | -0.419 | no |
| ARNIQA | TOPIQ-NR | 0.575 | 0.190 | -0.385 | no |
| ARNIQA | CLIP Quality | 0.464 | 0.080 | -0.383 | no |

Sign flips: 0.

API findings:

- Culling labels are NOT verified independent of the scores: treat Cⱼ and Nᵦ membership as provisional.
- Global labels are NOT verified independent: Gⱼ and Nₐ membership are provisional or unavailable.
- arniqa: role=global, G=0.376, C=0.547 (provisional)
- ava: role=culling, G=0.315, C=0.655 (provisional)
- clip_quality_v0: role=global, G=0.348, C=0.547 (provisional)
- liqe: role=both, G=0.557, C=0.731 (provisional)
- spaq: role=both, G=0.437, C=0.678 (provisional)
- topiq: role=global, G=0.416, C=0.599 (provisional)
- general × clip_quality_v0: pooled ρ=0.62 vs within-cluster ρ=0.18
- technical × clip_quality_v0: pooled ρ=0.60 vs within-cluster ρ=0.16
- arniqa × liqe: pooled ρ=0.59 vs within-cluster ρ=0.16
- Pairwise logistic ensemble on untouched test: accuracy 0.858, log loss 0.469, ECE 0.111.

Label notes:

- Fewer than 20 clusters with manual culling decisions; falling back to UNVERIFIED pick flags. Culling results are provisional until a human-labelled cohort exists.
- XMP ratings are unverified; pass trust_xmp_ratings once their origin is confirmed.
