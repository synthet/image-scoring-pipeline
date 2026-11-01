---
type: Plan
title: Owner-pick within-stack ranking — pre-registration
description: "Frozen design for #739: learn within-stack ranking weights from the owner's own export picks, with label source, features, model, metrics, baselines and the adoption threshold fixed before any evaluation output is read."
resource: docs/planning/owner-picks-ranking-preregistration.md
tags: [planning, culling, ranking, labels, preregistration]
timestamp: 2026-11-01T00:00:00Z
okf_version: 0.2
status: pre-registered
---

# Owner-pick within-stack ranking — pre-registration (#739)

This page fixes the design **before any evaluation output is read** (#739, AC-1). Any change after the
first evaluation output exists must be listed under [Revisions](#revisions) with its reason, and results
are reported against both the frozen and the revised design.

## Question

Do the owner's own export choices, learned as pairwise preferences over features we already compute,
pick the frame the owner chose more often than the current within-stack rankings do?

## Why this, and how it relates to other label work

- `images.pick_status` mirrors automated `cull_decision`, so it isn't an owner choice
  ([human culling labels](human-culling-labels.md), "Why").
- Model selection is label-free (`modules/score_analytics/model_selection.py`), and the current dedicated rank
  weights come from that label-free study (#474).
- [#415](human-culling-labels.md) builds a **prospective, blind** label set. This plan uses
  **retrospective, implicit** labels: frames the owner chose to export. The two are complementary. When #415
  has enough done groups, it is the independent check for the model fitted here.
- An external bird-culling survey (2026-11-01) names learning from one's own picks as the highest-leverage
  step for within-burst ranking.

## Labels

**Primary source: owner exports.** These are protected JPEG exports matched to RAW frames by the
near-duplicate study's inventory (image-scoring-skills `scripts/neardupe_study/library/inventory.py`). It
matches on capture second plus frame stem, using the frame-number rule plus an ORB visual check.

**Carousel picks, secondary tier only.** `carousel_stems()` reads stems from batch worklogs named
`jev-decision.json` and `carousel-pick.md`, so some may be Jev- or agent-assisted. A carousel stem enters the
secondary tier only where the worklog records an owner decision. Primary results never include it.

**Never used:** `images.pick_status`, `cull_decision`, agent cull recommendations, and LLM or Jev verdicts.

**Pairs.** For each stack, or sub-stack where one exists, that has at least one exported frame and at least
one non-exported frame:
- one pair for each (exported, non-exported) combination;
- stacks where every frame, or no frame, was exported are skipped;
- a stack contributes at most 20 pairs, chosen with seed `owner-picks-739`, so large bursts don't dominate.

Pair, stack and shoot counts are reported per capture year before fitting.

## Features (frozen)

Only values already stored or computed by existing code. A feature missing for an image is imputed as the
stack median and a `missing_<feature>` flag is added; it is not computed ad hoc for this study.

| Group | Features | Source |
|---|---|---|
| Quality models | `liqe`, `spaq`, `topiq`, `arniqa`, `ava` | `image_model_scores`; `PRODUCTION_MODELS` in `modules/score_analytics/model_selection.py` |
| CLIP quality | `clip_quality_v0` | `CULLING_ONLY_MODELS`, same module |
| Focus | noise-corrected sharpness and blur ratio | `modules/focus_quality.py` |
| Eye | eye keypoint presence and confidence | `modules/keypoints.py` (`eye-pose` keypoints) |
| Autofocus | AF point inside the bird box (yes / no / unknown) | `image_exif.af_metadata` (#726 backfill) and the current bird region |

Every feature enters as a **within-stack** value: rank or z-score inside its stack, never an absolute value.

## Model

A pairwise logistic regression on feature differences (exported minus non-exported), with no intercept,
L2-regularised, in scikit-learn. This is a RankNet-style linear ranker with no new dependency. The
regularisation strength is chosen by inner cross-validation on training years only.

## Evaluation

**Split:** leave one capture year out. Train on all other years and test on the held-out year. A year with
fewer than 30 eligible stacks is merged into its neighbour, chosen before fitting.

**Primary metric: top-1 agreement.** The share of test stacks whose highest-ranked frame is an exported
frame. Each stack is weighted equally.

**Secondary metrics:** pairwise accuracy over test pairs, and NDCG@3. These match #415's evaluation so the
results are comparable.

**Baselines,** scored on exactly the same test stacks:
1. `score_general`, the current within-stack rank;
2. the dedicated rank, `culling_rank`, with `DEFAULT_DEDICATED_RANK_WEIGHTS` (#474);
3. `blended_rank_value` with `clip_quality_v0` at the configured weight (default 0.15);
4. random ranking, as an expected-value floor.

**Uncertainty:** 95% confidence intervals by stack-level bootstrap, 2,000 resamples.

## Adoption rule (frozen)

Adopt only if **all** hold:
1. Pooled over held-out years, the top-1 lower 95% bound exceeds the **upper** 95% bound of the best
   baseline.
2. The learned model's top-1 is at or above the best baseline in at least two-thirds of held-out years.
3. No single feature group carries more than 80% of the learned weight mass, which guards against learning
   "the owner exports what `liqe` likes".

If adopted, the learned weights go into the `culling.dedicated_rank` config, which stays default-off. It
then runs in shadow beside the current rank on new shoots, and the owner switches it on explicitly. Nothing
changes production ranking automatically.

If not adopted, record the result and close #739 as a negative finding.

## Known risks

- **Selection bias:** only shoots the owner exported from are represented, and exports reflect composition
  and story as well as technical quality. Per-year results and the secondary tier make this visible; they
  don't remove it.
- **Ceiling:** burst-mates are often near-identical (see the near-duplicate retrospective), so even a
  perfect model can't reach 100% top-1.
- **Leakage:** stacks never cross the train/test split, because the split is by capture year.

## Revisions

None yet.
