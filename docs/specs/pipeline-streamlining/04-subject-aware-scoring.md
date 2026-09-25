---
type: Feature Spec
title: "Spec 04: subject-aware scoring"
description: Scoring consumes the localized subject — technical IQA models also score the primary subject crop, a versioned fusion blends subject and frame quality, and a crop-only backfill avoids a library rescore.
resource: docs/specs/pipeline-streamlining/04-subject-aware-scoring.md
tags: [specs, scoring, localization, iqa, fusion, migration]
timestamp: 2026-09-25T00:00:00Z
okf_version: 0.1
status: proposed
---

# Spec 04: subject-aware scoring

**Issue:** #409 · **Hub:** [INDEX.md](INDEX.md) · **Milestone:** M4 · **Depends on:** 01, 02, 03,
labelled bursts

## Summary

Production scores are full-frame. The models see the frame resized to 512–1024 px
(`scoring.models.*.max_dimension`), where a median bird covering 11.7% of the frame shrinks to
about 78 px at a 224 px model input. The evidence for scoring the subject:

- **Crop study** ([BIRD_BBOX_CROP_STUDY_2026-08-01.md](../../reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md)):
  degradation applied only to the subject lowers crop IQA 2.4–17.5× more than full-frame IQA.
- **Evidence probe** ([subject-evidence-probe-2026-09-24.md](../../reports/subject-evidence-probe-2026-09-24.md)):
  whole-frame scores are near chance for choosing within a burst.

This spec makes scoring a consumer of localization:
- The three PyTorch technical models (LIQE, TOPIQ, ARNIQA) also score the primary subject crop.
- A new **fusion v2** blends subject and frame quality.
- Composites are stored per fusion version.
- Existing full-frame rows are reused, so the library needs only a crop backfill, not a rescore.

## Users / stakeholders

- **Photographer / operator:** stars and picks reflect whether the subject is sharp, not just the
  scene.
- **Culling:** better within-burst ranking input.
- **Gallery:** reads `images.score_*` and `rating`, and needs a notice when fusion v2 is promoted.

## Product scenario

A burst of 12 eagle frames is scored. The frames share the scene, so their full-frame scores
barely differ. Their subject crops differ where focus and motion blur differ, and fusion v2 ranks
the sharp-eyed frames first.

A landscape with no subject gets the same composite it would get today, with `subject_mode = none`
recorded.

## Non-goals

- Aesthetic models on crops. SPAQ and AVA stay full-frame; composition belongs to the whole frame.
- Scoring more than the primary region.
- Changing star ratings or XMP sidecars automatically. Promotion is operator-triggered.
- Region scores for culling embeddings. The crop study found no benefit there.

## User stories

- As a photographer, I want a frame with a soft subject to score lower than a sharp one in the same
  burst.
- As an operator, I want to compare fusion v1 and v2 side by side before switching.
- As an operator, I want the switch to v2 to cost a crop backfill, not a library rescore.

## Design

### Crop

- **Region:** rank 0 of the current `subject_cascade` run (spec 03), or of the `bird` run while
  the cascade is disabled.
- **Source:** the inference rendition (spec 01), never the 512 px thumbnail.
- **Crop policy:** `score_subject_v1`, `pad_frac` 0.25. This is a proposal; the crop study found
  padded crops beat tight ones for embeddings.
- **Small subjects:** if the region covers less than 2% of the frame, or the crop's long edge is
  under 224 rendition pixels, `subject_mode = region_small`.

### Fusion v2 (proposal; weights tuned on labelled bursts)

The v1 weights and anchors are unchanged (`config.json` `scoring.fusion`, `percentile_anchors`).

```text
subject_technical = 0.40·n_crop(topiq) + 0.33·n_crop(arniqa) + 0.27·n_crop(liqe)
    (the v1 technical weights without spaq, renormalised; n_crop uses crop-specific anchors)

technical_v2 = (1 − α)·technical_v1 + α·subject_technical     α = 0.5
general_v2   = (1 − γ)·general_v1   + γ·subject_technical     γ = 0.25
aesthetic_v2 = aesthetic_v1

subject_mode ∈ {none, unavailable, region_small}  →  α = γ = 0  (v2 equals v1)
rating_v2 = existing rating_thresholds applied to general_v2
```

**Crop anchors:** p02 and p98 of each model's crop distribution. They are computed once from the
shadow backfill and stored with the fusion version, just as `percentile_anchors` are today.

### Storage

- **`image_model_scores`:** gains `input_mode` (`full_frame` | `region`), `region_id`,
  `crop_policy` and `rendition_hash`. The primary key becomes `(image_id, model_name, input_mode)`.
- **New table `image_composite_scores`:** `(image_id, fusion_version)` primary key, plus
  `general`, `technical`, `aesthetic`, `rating`, `subject_mode`, `region_id` and `computed_at`.
- **`images.score_*`:** keeps holding the authoritative version. `images.score_fusion_version`
  records which version that is.

## Acceptance criteria

- **AC-1** — The migration shall add `input_mode` with default `full_frame` to
  `image_model_scores`, and extend its primary key to `(image_id, model_name, input_mode)`.
- **AC-2** — After the migration, every existing `image_model_scores` row shall have `input_mode =
  full_frame`.
- **AC-3** — Scoring completeness predicates shall count only rows with `input_mode = full_frame`
  and `is_shadow = false`.
- **AC-4** — Fusion v1 shall read only rows with `input_mode = full_frame` and `is_shadow = false`.
- **AC-5** — Where `scoring.subject.enabled` is true and an image has a current primary region,
  the scoring runner shall score the subject crop with LIQE, TOPIQ and ARNIQA.
- **AC-6** — The scoring runner shall store each crop score with `input_mode = region`, the region
  id, the crop policy and the rendition hash.
- **AC-7** — If an image has no current localization attempt, then the scoring runner shall record
  `subject_mode = unavailable`.
- **AC-8** — If the image's current localization attempt is `no_detection`, then the scoring
  runner shall record `subject_mode = none`.
- **AC-9** — If the primary region is under 2% of the frame or its crop's long edge is under 224
  pixels, then the scoring runner shall record `subject_mode = region_small`.
- **AC-10** — When scoring completes for an image, the system shall write one
  `image_composite_scores` row per enabled fusion version.
- **AC-11** — While `subject_mode` is not `region`, fusion v2 shall produce the same general,
  technical and aesthetic values as fusion v1.
- **AC-12** — While `scoring.fusion_version` is `v1`, the system shall keep writing
  `images.score_*` and `images.rating` from fusion v1.
- **AC-13** — When a localization attempt for an image moves from `retryable_error` to `detected`,
  the system shall queue crop scoring for that image without re-running full-frame models.
- **AC-14** — When a primary region's geometry or rendition hash changes, the system shall mark
  that image's `region` rows stale.
- **AC-15** — The crop backfill job shall score only images that have a current primary region and
  no current `region` rows for the active crop policy.
- **AC-16** — The crop backfill job shall report the planned image count and an estimated GPU time
  before it runs.
- **AC-17** — When an operator requests a fusion recompute, the system shall compute composites from
  stored rows without running any model.
- **AC-18** — When `scoring.fusion_version` changes, the system shall require an explicit
  operator-triggered job to rewrite `images.score_*` and `images.rating`.
- **AC-19** — The rating-rewrite job shall report the number of images whose star rating would
  change before it writes.
- **AC-20** — If an image's XMP rating differs from its last pipeline-written rating, then the
  rating-rewrite job shall not overwrite that XMP rating.
- **AC-21** — The evaluation script shall report best-vs-reject pairwise AUC for fusion v1 and v2
  on the labelled-burst set, with a paired-bootstrap 95% confidence interval of the difference.
- **AC-22** — The system shall not allow `scoring.fusion_version = v2` as a default until AC-21's
  lower confidence bound for (v2 − v1) is above zero on ≥ 300 labelled bursts.

## Assumptions and dependencies

- **Spec 01:** crops come from the inference rendition.
- **Spec 02:** the attempt-before edge supplies an attempt for each image (AC-7, AC-8).
- **Spec 03:** until AC-18 of spec 03 passes, crop scoring runs in shadow only.
- **Other readers of `image_model_scores`:** as of 2026-09-25, about 20 backend modules read the
  table, including `scoring.py`, `db_legacy.py`, `api_helpers.py`, `score_analytics/`,
  `agent_cull/payload.py` and `mcp/tool_support.py`. The gallery reads it in `electron/db.ts`,
  `electron/sortColumns.ts` and `electron/sortSql.ts`. Every reader must be audited for the new
  `input_mode` filter before the migration ships. Otherwise a `region` row could leak into a sort
  or a completeness check. That makes this a cross-repo contract change.
- **Labelled bursts:** the ~300-burst human set (step 0 of
  [subject-aware-culling-evidence.md](../../planning/subject-aware-culling-evidence.md)) exists
  before AC-22 is evaluated.
- **XMP:** AC-20 assumes the last pipeline-written rating can be recovered. If it can't, the
  rewrite job needs a stored copy first.

## Open questions

Recommendations and deadlines: [07 — decision register](07-blockers-and-decisions.md#3-decision-register) (O-1 to O-5, and the sibling-table alternative in §4.3).

1. What values of α, γ and `pad_frac` to use? These are proposals, tuned on the labelled bursts
   and never on the evaluation split.
2. Should `region_small` get a reduced α instead of zero? The probe found crop focus below chance
   on small subjects, so zero is the safe default.
3. Should SPAQ (MUSIQ, TensorFlow) also score crops? It carries 0.25 of v1 technical weight, but
   crop-scoring it costs a TF pass per image.
4. Should `image_composite_scores` be exposed through the API so the gallery can show v1 and v2
   side by side?

## Implementation plan

**Goal:** AC-1 to AC-21 pass in shadow. AC-22 gates promotion.

**Files:**
- New migration in `migrations/versions/`: `input_mode`, `region_id`, `crop_policy`,
  `rendition_hash`; `image_composite_scores`; `images.score_fusion_version`. Mirrored in
  `modules/db_postgres.py`.
- `modules/score_normalization.py`: `compute_composites_v2` and crop anchors.
- `modules/scoring.py` and `modules/engines/host.py`: the crop pass.
- `modules/db_legacy.py`: completeness SQL filters.
- New `scripts/maintenance/backfill_subject_scores.py`: crop backfill and recompute.
- New `scripts/research/eval_fusion_bursts.py`: AC-21.
- Docs: [scoring.md](../../architecture/pipeline/phases/scoring.md) and DB_SCHEMA.

**Approach:**
1. Migration and reader audit in both repos, with filters added. No behaviour change.
2. Crop pass in shadow; composites written for v1 and v2.
3. Backfill with dry-run counts; compute crop anchors.
4. Labelled-burst evaluation.
5. If AC-22 passes: operator promotion, recompute, then rating rewrite with dry-run.

**Tests to write first:**
- `tests/test_image_model_scores_input_mode.py`: AC-1 to AC-4 (Postgres).
- `tests/test_subject_scoring_modes.py`: AC-5 to AC-9, with stub models.
- `tests/test_fusion_v2.py`: AC-10, AC-11, AC-12, AC-17, as pure functions.
- `tests/test_subject_score_invalidation.py`: AC-13, AC-14.
- `tests/test_subject_backfill.py`: AC-15, AC-16.
- `tests/test_rating_rewrite.py`: AC-18 to AC-20.

**Rollback:** set `scoring.subject.enabled=false` and `scoring.fusion_version=v1`, then run the
recompute. `region` rows and v2 composites stay as history, and no model re-run is needed.
