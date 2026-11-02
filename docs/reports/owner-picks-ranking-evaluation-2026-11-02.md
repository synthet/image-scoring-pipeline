---
type: Report
title: Owner-pick within-stack ranking — evaluation (negative)
description: "Pre-registered evaluation for #739: a pairwise ranker learned from the owner's exports does not beat the current within-stack rank on held-out years; not adopted. The default-off dedicated rank (#474) also does not beat score_general on owner picks."
resource: docs/reports/owner-picks-ranking-evaluation-2026-11-02.md
tags: [reports, culling, ranking, labels, evaluation]
timestamp: 2026-11-02T00:00:00Z
okf_version: 0.2
---

# Owner-pick within-stack ranking — evaluation (2026-11-02)

**Decision: not adopted** (#739). The run followed the
[pre-registration](../planning/owner-picks-ranking-preregistration.md), including revision R1. The script
is `scripts/analysis/owner_picks_ranking_eval.py`, run read-only in gpu-shell on CPU.

## Labels

- **Primary:** exported JPEGs whose camera frame stem and capture second both match a RAW frame. That gives
  275 frames in 178 eligible stacks and 1,249 pairs (at most 20 per stack), all from 2025 and 2026.
- **Secondary (R1):** the primary labels plus exports matched by capture second alone, admitted only when
  exactly one DB frame has that second. That adds 285 frames, for 350 stacks from 2014–2026.
- 31 exports had no readable EXIF time.
- No carousel picks were used, because no owner-only carousel record exists.
- 2024 is absent from the DB.

**Features:**
- the quality models `liqe`, `spaq`, `topiq`, `arniqa` and `ava`;
- `clip_quality_v0`;
- eye keypoint confidence and visibility;
- AF centre inside the bird box. This is unknown for rotated frames, or where AF metadata or a bird box is
  missing.

All features are z-scored within the stack, with stack-median imputation and missing-value flags.
Noise-corrected focus sharpness isn't stored in the DB, so it was excluded under the frozen rule.

## Results: primary tier (decides adoption)

Leave one year out, two folds (2025 and 2026). Each stack counts equally. The 95% intervals come from a
stack bootstrap with 2,000 resamples.

| Method | Top-1 | 95% CI | Pairwise acc. | NDCG@3 |
|---|---|---|---|---|
| `score_general` (current rank) | **0.407** | 0.334–0.478 | 0.673 | 0.569 |
| CLIP blend (`blended_rank_value`, weight 0.15) | 0.393 | 0.320–0.466 | 0.653 | 0.567 |
| Dedicated rank (#474 weights) | 0.374 | 0.303–0.447 | 0.676 | 0.556 |
| **Learned (pairwise logistic)** | 0.371 | 0.298–0.444 | 0.665 | 0.565 |
| Random | 0.276 | 0.249–0.302 | — | — |

| Held-out year | Stacks | Learned | Best baseline (`score_general`) |
|---|---|---|---|
| 2025 | 65 | 0.385 | 0.338 |
| 2026 | 113 | 0.363 | 0.447 |

**Adoption rule:**
1. The learned model's lower CI bound must clear the best baseline's upper bound: **fails**, the intervals
   overlap.
2. It must win at least two-thirds of the years: **fails**, 1 of 2.
3. No feature group may carry more than 80% of the weight: **passes**. The weight shares are quality 60%,
   eye 21%, AF 15% and CLIP 4%.

## Results: secondary tier (reported only)

350 stacks in four folds (2014–2021 merged, 2022–2023, 2025 and 2026):

| Method | Top-1 | 95% CI |
|---|---|---|
| `score_general` | 0.450 | 0.400–0.503 |
| Learned | 0.449 | 0.394–0.500 |
| CLIP blend | 0.449 | 0.397–0.497 |
| Dedicated rank | 0.430 | 0.379–0.480 |
| Random | 0.357 | 0.339–0.375 |

The learned model won 2 of 4 folds, both from the older years, and lost 2025 and 2026. That's the same
picture as the primary tier.

## Interpretation

- Every ranking beats random, so the existing scores do carry owner-preference signal.
- A linear model over these features can't separate the owner's export from its stack-mates any better
  than `score_general` does. That's consistent with the near-duplicate retrospective: burst-mates differ by
  sub-visible quality.
- **On owner picks, the default-off dedicated rank (#474) doesn't beat `score_general`.** That's evidence
  against enabling `culling.dedicated_rank`.
- The labels are limited: only exported shoots are represented, and two-thirds of the primary stacks are
  from 2026. A larger owner-label set, such as #415's blind labels, is the next evidence source.
