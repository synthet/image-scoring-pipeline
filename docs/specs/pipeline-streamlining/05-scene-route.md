---
type: Feature Spec
title: "Spec 05: scene route"
description: Zero-shot scene classification from the stored CLIP image vector, benchmarked first, then used to choose which detector and species model run for each image.
resource: docs/specs/pipeline-streamlining/05-scene-route.md
tags: [specs, pipeline, clip, scene, routing, localization]
timestamp: 2026-09-25T00:00:00Z
okf_version: 0.1
status: proposed
---

# Spec 05: scene route

**Issue:** #412 · **Hub:** [INDEX.md](INDEX.md) · **Milestone:** M2 (benchmark), then M3

## Summary

Today every image in a localization scope gets the wildlife detector, and species runs only on
images tagged `birds`. A **scene route** classifies each image before localization, so the
pipeline can:
- choose the detector (the wildlife cascade, or none);
- choose the species taxon (spec 06);
- skip work that can't help, such as wildlife detection on a cityscape.

It is nearly free, because `KeywordScorer._score_prompts_from_embedding` (`modules/tagging.py`)
already scores text prompts against the persisted 512-d `clip_vit_b32_image` vector without
re-reading the image.

The main risk is a **false skip**: a small bird in a landscape routed as `landscape` and never
localized. Routing therefore skips detection only at high confidence, and the benchmark measures
wildlife recall at that threshold first.

## Users / stakeholders

- **Localization and species phases:** receive provider and taxon hints.
- **Operator:** gets a filterable scene facet and less wasted GPU time.
- **Scoring (spec 04):** a confident non-wildlife scene yields `subject_mode = none` without a
  detector pass.

## Product scenario

- **Wildlife:** a mixed folder of wildlife, landscapes and street shots is ingested. The wildlife
  frames go through the detector cascade.
- **Confident landscape:** a landscape at probability 0.97 skips detection and is recorded as
  routed.
- **Ambiguous frame:** a marsh scene with a distant heron, at 0.55 landscape and 0.40 wildlife, is
  below the skip threshold, so it still gets the cascade.

## Non-goals

- A new vision model. The route uses the existing CLIP ViT-B/32 vector.
- Person or face detection.
- Replacing keywords. The scene label is stored separately, with an optional keyword projection.

## Scene labels (v1, proposal)

| Label | Routes to |
|---|---|
| `wildlife_bird` | detector cascade (spec 03), species taxon Aves |
| `wildlife_mammal` | detector cascade, taxon Mammalia |
| `wildlife_insect` | species only (full frame) until an open-vocabulary detector exists; taxon Insecta |
| `wildlife_herp` | species only (full frame) until an open-vocabulary detector exists; taxon Reptilia/Amphibia |
| `landscape` | skip detection when confident |
| `architecture` | skip detection when confident |
| `people` | skip wildlife detection when confident |
| `other` | detector cascade (the safe default) |

Each label is scored with an ensemble of 3–5 prompts, such as "a photo of a bird in the wild" or "a
wildlife photograph of a bird". Probabilities come from a softmax over the label set at the CLIP
logit scale, the same way keyword confidences are computed today.

## Acceptance criteria

- **AC-1** — The benchmark script shall score a labelled sample of ≥ 50 images per scene label from
  their stored CLIP vectors, without decoding any image.
- **AC-2** — The benchmark script shall report per-label precision and recall, and a confusion
  matrix.
- **AC-3** — The benchmark script shall report, for each candidate skip threshold, the fraction of
  human-labelled wildlife images that would skip detection.
- **AC-4** — The system shall not enable detection skipping until the chosen threshold skips ≤ 2%
  of human-labelled wildlife images.
- **AC-5** — Where `scene_route.enabled` is true, the system shall persist one scene
  classification per image with the prompt-set version, the embedding space, all label
  probabilities and the top label.
- **AC-6** — If an image has no stored CLIP vector, then the scene route shall compute and persist
  the vector before classifying.
- **AC-7** — When the top label is `landscape`, `architecture` or `people` with probability ≥
  `scene_route.skip_detection_min_prob`, the localization planner shall record a `disabled`
  attempt with reason `scene_route` instead of running wildlife detectors.
- **AC-8** — If the top label's probability is below `scene_route.skip_detection_min_prob`, then
  the localization planner shall run the detector cascade.
- **AC-9** — When the prompt-set version changes, the system shall treat existing scene
  classifications as stale.
- **AC-10** — When a scene classification changes from a skip label to a wildlife label, the system
  shall reopen the image's localization work.

## Assumptions and dependencies

- The `clip_vit_b32_image` space exists for most images today. It is written by the culling and
  tagging paths.
- A `disabled` attempt with a reason satisfies the attempt-before edge (spec 02, AC-6), so a routed
  skip never blocks scoring.
- **Storage:** a new table `image_scene_labels (image_id, scene_version, top_label, top_prob,
  probs JSONB, embedding_space, created_at)`, with `(image_id, scene_version)` as the primary key.
  An optional `scene:<label>` keyword projection is written with `source = 'scene_route'`.
- **Labels:** a stratified human sample is required. The scene labels can be collected in the same
  labelling pass as the burst set.

## Open questions

Recommendations and deadlines: [07 — decision register](07-blockers-and-decisions.md#3-decision-register) (SR-1 to SR-4).

1. Single-label, or multi-label for mixed scenes such as people with architecture? The proposal is
   to store all probabilities and route on the top label.
2. Is ViT-B/32 accurate enough, or is the stored OpenCLIP ViT-L/14 image space (used by two-level
   culling) better at the same near-zero cost? Benchmark both vectors.
3. Should `people` scenes later route to a person detector for subject-aware scoring of portraits?
   That would be a separate spec.

## Implementation plan

**Goal:** first the benchmark (AC-1 to AC-4); then AC-5 to AC-10 behind `scene_route.enabled`.

**Files:**
- New `modules/scene_route.py`: label set, prompt ensembles, and `classify(embedding)`.
- New `scripts/research/scene_route_benchmark.py`: AC-1 to AC-3.
- A migration plus `modules/db_postgres.py`: `image_scene_labels`.
- `modules/localization_runner.py`: AC-7, AC-8.

**Approach:**
1. Collect the labelled sample.
2. Benchmark on ViT-B/32 and OpenCLIP L/14.
3. Choose the space and threshold, and document the result in `docs/reports/`.
4. Add persistence.
5. Add routing in localization.

**Tests to write first:**
- `tests/test_scene_route_classify.py`: probabilities, versioning, staleness (AC-5, AC-9).
- `tests/test_scene_route_localization.py`: skip versus run at the threshold, and the `disabled`
  attempt reason (AC-7, AC-8, AC-10).

**Rollback:** set `scene_route.enabled=false`. Localization then runs the cascade on every image in
scope, and stored classifications stay as history.
