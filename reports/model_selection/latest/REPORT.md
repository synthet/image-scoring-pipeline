# Model selection report (label-free)

Scope: `{'kind': 'library'}` · 77,331 images · 11,174 stacks (66,308 images, ≥ 2 per stack). Snapshot `1f1f407b32b372f0`, git `75b53e8e5e`, generated 2026-10-02T01:20:03.070432+00:00.

> **Statistical only; not validated against human judgments.** No independent human labels were used. Every number below measures agreement between models, redundancy or resolution. When models disagree inside a stack, this report cannot say which one is right. `stacks.best_image_id` and pick status are derived from `score_general`, so agreement with them is agreement with current production, not accuracy.

## Recommended model sets

Greedy forward selection: add the model that best reproduces the scenario target; stop when the next model adds less than 0.01 (max 3).

| Scenario | Target | 1 model | 2 models | 3 models | Stop reason |
|---|---|---|---|---|---|
| general | Spearman with the full general composite | liqe (0.836) | liqe + spaq (0.978) | — | next best (ava) adds gain 0.0085 < 0.01 |
| technical | Spearman with the full technical composite | topiq (0.843) | topiq + arniqa (0.909) | topiq + arniqa + spaq (0.970) | reached 3 models |
| aesthetic | Spearman with the full aesthetic composite | spaq (0.872) | spaq + ava (0.992) | — | next best (liqe) adds gain 0.0077 < 0.01 |
| culling | mean within-stack τ-b with the all-candidate consensus rank | topiq (0.524) | topiq + liqe (0.677) | topiq + liqe + ava (0.714) | reached 3 models |

## Verdicts

### general

| Model | Verdict | Reasons |
|---|---|---|
| arniqa | **keep** | dropping it changes 6.8% of star ratings |
| ava | **keep** | dropping it changes 14.3% of star ratings; carries its own principal component (PC2, loading -0.85, 17% of variance); carries its own principal component (PC3, loading +0.41, 12% of variance) |
| liqe | **keep** | dropping it changes 29.0% of star ratings |
| spaq | **keep** | dropping it changes 27.5% of star ratings; carries its own principal component (PC3, loading -0.85, 12% of variance) |
| topiq | **keep** | dropping it changes 7.6% of star ratings |

### technical

| Model | Verdict | Reasons |
|---|---|---|
| arniqa | **keep** | dropping it changes 9.1% of colour labels |
| liqe | **keep** | dropping it changes 8.2% of colour labels |
| spaq | **keep** | dropping it changes 14.5% of colour labels; carries its own principal component (PC3, loading -0.85, 12% of variance) |
| topiq | **keep** | dropping it changes 9.9% of colour labels |

### aesthetic

| Model | Verdict | Reasons |
|---|---|---|
| ava | **keep** | dropping it changes 12.6% of colour labels; carries its own principal component (PC2, loading -0.85, 17% of variance); carries its own principal component (PC3, loading +0.41, 12% of variance) |
| liqe | **optional** | without it Spearman 0.992; ratings change 0.0%, labels 2.5% |
| spaq | **keep** | dropping it changes 18.2% of colour labels; carries its own principal component (PC3, loading -0.85, 12% of variance) |

### culling

| Model | Verdict | Reasons |
|---|---|---|
| liqe | **optional** | within-stack share below median |
| spaq | **optional** | within-stack share below median |
| topiq | **keep** | within-stack share 0.09 and consensus τ-b 0.23 in the top half; ties 0.5% |
| arniqa | **optional** | consensus τ-b below median |
| ava | **optional** | within-stack share below median; consensus τ-b below median |
| clip_quality_v0 | **optional** | consensus τ-b below median |

## Composite drop-one ablation

Composite recomputed without one model, using the configured `scoring.fusion` weights and percentile anchors (weights re-normalized over the remaining models). `everywhere` removes the model from every composite.

| Composite | Model | Weight share | Spearman vs full | Mean abs shift | Ratings changed | Labels changed | Top-10% overlap | Stack best frame changed |
|---|---|---|---|---|---|---|---|---|
| general | arniqa | 10.0% | 0.9958 | 0.0135 | 6.8% | 0.0% | 92.6% | 10.4% |
| general | ava | 12.0% | 0.9892 | 0.0275 | 14.3% | 0.0% | 84.1% | 10.9% |
| general | liqe | 35.0% | 0.8964 | 0.0604 | 29.0% | 0.0% | 72.5% | 24.5% |
| general | spaq | 30.0% | 0.9141 | 0.0569 | 27.5% | 0.0% | 75.2% | 27.8% |
| general | topiq | 13.0% | 0.9944 | 0.0151 | 7.6% | 0.0% | 92.2% | 9.7% |
| technical | arniqa | 25.0% | 0.9732 | 0.0328 | 0.0% | 9.1% | 81.0% | 23.4% |
| technical | liqe | 20.0% | 0.9703 | 0.0301 | 0.0% | 8.2% | 84.8% | 13.5% |
| technical | spaq | 25.0% | 0.9358 | 0.0462 | 0.0% | 14.5% | 75.1% | 22.8% |
| technical | topiq | 30.0% | 0.9685 | 0.0335 | 0.0% | 9.9% | 80.6% | 19.5% |
| aesthetic | ava | 40.0% | 0.8955 | 0.0972 | 0.0% | 12.6% | 50.2% | 29.3% |
| aesthetic | liqe | 10.0% | 0.9923 | 0.0210 | 0.0% | 2.5% | 90.9% | 6.6% |
| aesthetic | spaq | 50.0% | 0.7637 | 0.1149 | 0.0% | 18.2% | 66.3% | 38.0% |
| everywhere | arniqa | — | 0.9732 | 0.0135 | 6.8% | 9.1% | 92.6% | 10.4% |
| everywhere | ava | — | 0.8955 | 0.0275 | 14.3% | 12.6% | 84.1% | 10.9% |
| everywhere | liqe | — | 0.8964 | 0.0604 | 29.0% | 10.9% | 72.5% | 24.5% |
| everywhere | spaq | — | 0.7637 | 0.0569 | 27.5% | 29.8% | 75.2% | 27.8% |
| everywhere | topiq | — | 0.9685 | 0.0151 | 7.6% | 9.9% | 92.2% | 9.7% |

Recomputed (current weights) vs stored composite Spearman: general 1.0000, technical 1.0000, aesthetic 1.0000. Values well below 1 mean stored composites predate the current weights or anchors.

## Within-stack (culling) signal

Consensus = leave-one-out mean within-stack rank of the other culling candidates, on 11,174 stacks (66,308 images) where every candidate is scored. Ties = identical stored values.

| Dimension | Role | Within-stack variance share | Tie rate | Top-gap z | Consensus τ-b [95% CI] | Top-1 agreement | Top tied | Matches production best frame |
|---|---|---|---|---|---|---|---|---|
| general | composite | 0.066 | 0.1% | 1.271 | — | — | — | 95.8% |
| technical | composite | 0.070 | 0.1% | 1.269 | — | — | — | 74.7% |
| aesthetic | composite | 0.074 | 0.1% | 1.286 | — | — | — | 69.3% |
| arniqa | candidate | 0.099 | 0.6% | 1.293 | 0.136 [0.129, 0.150] | 41.3% | 0.8% | 45.0% |
| ava | candidate | 0.084 | 2.1% | 1.307 | 0.100 [0.089, 0.112] | 39.7% | 3.9% | 45.8% |
| clip_quality_v0 | culling_candidate | 0.104 | 0.0% | 1.304 | 0.133 [0.119, 0.142] | 40.9% | 0.0% | 39.4% |
| koniq | legacy | 0.031 | 13.2% | 1.389 | — | — | — | 47.1% |
| liqe | candidate | 0.065 | 0.4% | 1.251 | 0.226 [0.215, 0.239] | 46.2% | 1.0% | 61.8% |
| paq2piq | legacy | 0.010 | 13.9% | 1.359 | — | — | — | 47.5% |
| spaq | candidate | 0.081 | 1.3% | 1.271 | 0.137 [0.125, 0.147] | 41.5% | 1.9% | 60.2% |
| topiq | candidate | 0.087 | 0.5% | 1.267 | 0.233 [0.221, 0.241] | 46.8% | 0.9% | 50.3% |
| refcull_composite | research_family | 0.175 | 9.1% | 1.230 | — | — | — | 36.2% |
| refcull_composition | research_family | 0.209 | 12.7% | 1.213 | — | — | — | 32.7% |
| refcull_context | research_family | 0.204 | 14.9% | 1.149 | — | — | — | 32.9% |
| refcull_exposure | research_family | 0.197 | 14.3% | 1.239 | — | — | — | 34.8% |
| refcull_eye | research_family | 0.251 | 13.5% | 1.154 | — | — | — | 35.2% |
| refcull_focus | research_family | 0.289 | 13.0% | 1.119 | — | — | — | 36.6% |
| refcull_noise | research_family | 0.180 | 25.5% | 1.058 | — | — | — | 32.2% |

## Redundancy (|ρ| ≥ 0.8)

- **Library (pooled Spearman):** {general, technical, aesthetic, liqe, spaq, topiq} (general–technical 0.96, general–aesthetic 0.83, general–liqe 0.84, technical–topiq 0.84, aesthetic–spaq 0.87)
- **Within stack (rank-centred Spearman):** {general, technical} (general–technical 0.83)

Largest library vs within-stack differences:

| Pair | Library ρ | Within-stack ρ | Δ | Sign flip |
|---|---|---|---|---|
| general – clip_quality_v0 | 0.616 | 0.184 | -0.432 | no |
| technical – clip_quality_v0 | 0.595 | 0.164 | -0.431 | no |
| arniqa – liqe | 0.587 | 0.162 | -0.426 | no |
| clip_quality_v0 – liqe | 0.618 | 0.199 | -0.419 | no |
| arniqa – topiq | 0.575 | 0.190 | -0.385 | no |
| arniqa – clip_quality_v0 | 0.464 | 0.080 | -0.383 | no |
| koniq – spaq | 0.560 | 0.199 | -0.361 | no |
| technical – paq2piq | 0.560 | 0.206 | -0.354 | no |
| koniq – paq2piq | 0.589 | 0.238 | -0.351 | no |
| liqe – topiq | 0.662 | 0.313 | -0.349 | no |
| technical – koniq | 0.556 | 0.216 | -0.340 | no |
| aesthetic – koniq | 0.564 | 0.224 | -0.340 | no |

## PCA of production models (n = 77,331 complete rows)

| Model | PC1 (59%) | PC2 (17%) | PC3 (12%) | PC4 (7%) |
|---|---|---|---|---|
| liqe | -0.49 | +0.23 | +0.30 | -0.50 |
| spaq | -0.41 | -0.28 | -0.85 | +0.00 |
| topiq | -0.51 | +0.23 | -0.01 | -0.31 |
| arniqa | -0.48 | +0.30 | +0.15 | +0.81 |
| ava | -0.31 | -0.85 | +0.41 | +0.06 |

## Distribution health

| Dimension | Role | Coverage | Floor | Ceiling | Distinct-value tie fraction | On 2-decimal grid | Entropy | Failed | Not loaded |
|---|---|---|---|---|---|---|---|---|---|
| general | composite | 100.00% | 0.00% | 0.00% | 0.889 | 1.0% | 0.910 | —% | —% |
| technical | composite | 100.00% | 0.00% | 0.01% | 0.888 | 1.0% | 0.906 | —% | —% |
| aesthetic | composite | 100.00% | 0.00% | 0.02% | 0.887 | 1.0% | 0.926 | —% | —% |
| arniqa | candidate | 100.00% | 0.00% | 0.00% | 0.948 | 2.9% | 0.630 | 0.00% | 0.00% |
| ava | candidate | 100.00% | 0.00% | 0.00% | 0.994 | 10.1% | 0.608 | 0.00% | 0.00% |
| clip_quality_v0 | culling_candidate | 99.95% | 0.00% | 0.00% | 0.039 | 0.1% | 0.836 | 0.00% | 0.00% |
| koniq | legacy | 49.18% | 3.69% | 0.00% | 0.986 | 13.3% | 0.757 | 0.00% | 0.00% |
| liqe | candidate | 100.00% | 0.00% | 0.22% | 0.206 | 2.3% | 0.865 | 0.00% | 0.00% |
| paq2piq | legacy | 49.18% | 3.69% | 0.00% | 0.991 | 13.2% | 0.572 | 0.00% | 0.00% |
| spaq | candidate | 100.00% | 0.00% | 0.00% | 0.991 | 10.1% | 0.815 | 0.00% | 0.00% |
| topiq | candidate | 100.00% | 0.00% | 0.00% | 0.942 | 2.9% | 0.667 | 0.00% | 0.00% |
| refcull_composite | research_family | 99.31% | 0.00% | 0.00% | 0.999 | 0.0% | 0.774 | 0.00% | 0.00% |
| refcull_composition | research_family | 99.31% | 0.00% | 0.00% | 0.999 | 0.1% | 0.728 | 0.00% | 0.00% |
| refcull_context | research_family | 99.31% | 0.00% | 0.00% | 0.999 | 0.0% | 0.711 | 0.00% | 0.00% |
| refcull_exposure | research_family | 99.31% | 1.34% | 0.00% | 0.999 | 4.5% | 0.696 | 0.00% | 0.00% |
| refcull_eye | research_family | 99.31% | 0.00% | 0.00% | 0.999 | 6.0% | 0.734 | 0.00% | 0.00% |
| refcull_focus | research_family | 99.31% | 0.00% | 0.00% | 0.999 | 0.0% | 0.696 | 0.00% | 0.00% |
| refcull_noise | research_family | 99.31% | 0.00% | 0.00% | 0.999 | 1.3% | 0.744 | 0.00% | 0.00% |

## Cost (estimated)

Not measured: no GPU benchmark was run. Architecture facts come from `modules/engines/*`; parameter counts and relative cost are approximate.

| Model | Runtime | Architecture | Params | Input | Shared backbone | Relative cost | Observed median s (n) |
|---|---|---|---|---|---|---|---|
| liqe | PyTorch (pyiqa) | CLIP ViT-B/32 image tower + cached text prompts | ~88M (image tower) | 224 px crops | none in production | medium | — |
| topiq | PyTorch (pyiqa) | TOPIQ-NR, ResNet-50 multi-scale features | ~45M | full image (resized) | none | medium | — |
| arniqa | PyTorch (pyiqa) | ARNIQA, ResNet-50 encoder + linear regressor at 2 scales | ~24M | full + half resolution | none | medium | — |
| spaq | TensorFlow (MUSIQ) | MUSIQ multi-scale transformer, SPAQ checkpoint | ~27M | multi-scale patches of the full image | TF session shared with ava | high | — |
| ava | TensorFlow (MUSIQ) | MUSIQ multi-scale transformer, AVA checkpoint | ~27M | multi-scale patches of the full image | TF session shared with spaq | high | — |
| clip_quality_v0 | PyTorch (CLIP text tower) | prompt similarity on stored clip_vit_b32_image embeddings | text tower only | existing 512-d embedding | keywords-phase CLIP embedding | near zero when the embedding exists | — |

Observed timings: images.scores_json is not present; per-model timings are not persisted.

## Reference-only dimensions (no verdict)

Composites are built from the candidates; `koniq` / `paq2piq` are deprecated and cover part of the library; `refcull_*` is a derived research family (`refcull_composite` is built from the others). Pairwise statistics involving them use only images scored by both sides.

- `general` — composite, coverage 100.00%
- `technical` — composite, coverage 100.00%
- `aesthetic` — composite, coverage 100.00%
- `koniq` — legacy, coverage 49.18%
- `paq2piq` — legacy, coverage 49.18%
- `refcull_composite` — research_family, coverage 99.31%
- `refcull_composition` — research_family, coverage 99.31%
- `refcull_context` — research_family, coverage 99.31%
- `refcull_exposure` — research_family, coverage 99.31%
- `refcull_eye` — research_family, coverage 99.31%
- `refcull_focus` — research_family, coverage 99.31%
- `refcull_noise` — research_family, coverage 99.31%

## Rules (fixed before running)

- **Composite omittable:** Spearman ≥ 0.98 with the full composite, star ratings changed < 2% and colour labels changed < 2%.
- **Composite keep:** dropping changes ≥ 5% of the composite's output (ratings for `general`, labels for `technical` / `aesthetic`), or the model loads ≥ 0.4 on a component beyond PC1 with ≥ 10% of variance.
- **Culling keep:** within-stack variance share and consensus τ-b at or above the candidate median and tie rate < 20%; a keep with within-stack ρ ≥ 0.8 to a better-agreeing keep is demoted to omittable.
- **Culling omittable:** tie rate ≥ 50%, or within-stack ρ ≥ 0.8 with a kept model.
- Everything else is **optional**.
