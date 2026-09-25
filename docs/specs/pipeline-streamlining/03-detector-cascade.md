---
type: Feature Spec
title: "Spec 03: detector cascade"
description: A shadow localization provider that combines the bird YOLO with an open COCO detector (RTMDet-tiny) and a small-box YOLO refine, raising recall without the false positives of YOLO at 1280.
resource: docs/specs/pipeline-streamlining/03-detector-cascade.md
tags: [specs, localization, detection, bird-detection, rtmdet, onnx]
timestamp: 2026-09-25T00:00:00Z
okf_version: 0.1
status: proposed
---

# Spec 03: detector cascade

**Issue:** #408 · **Hub:** [INDEX.md](INDEX.md) · **Milestone:** M2

## Summary

Subject-aware scoring (spec 04) turns detector errors into score errors: a miss falls back to full
frame, and a false box scores background sharpness. On the #377 cohort the production YOLO-640
draws good boxes but finds too few birds, and YOLO-1280 finds birds but adds false boxes.

**Recall on the independent strata:**
- YOLO-640: 20/137.
- YOLO-1280: 112/137 (82%), with 45/71 false positives.
- COCO RTMDet-tiny, animal classes: 127/137 at its default policy, with 12/71 false positives.
- RTMDet at the threshold that matches YOLO-1280's recall: a 4% false-positive rate.

**Box quality:** YOLO-640 boxes are 73% tight, and 45/48 on small birds. RTMDet is weak on small
birds: 28/48 tight.

This spec adds RTMDet-tiny as a second provider and a cascade provider that combines the two. It
also adds a YOLO refine pass on small fallback boxes. Everything is shadow only.

Sources: [detector-benchmark-2026-09.md](../../reports/detector-benchmark-2026-09.md),
[subject-detector-comparison-2026-09-24.md](../../reports/subject-detector-comparison-2026-09-24.md),
[bbox-llm-judge-panel-2026-09-24.md](../../reports/bbox-llm-judge-panel-2026-09-24.md).

## Users / stakeholders

- **Spec 04 (scoring) and rollout stage 5 (BioCLIP):** receive better regions.
- **Operator:** gets per-provider diagnostics.
- **image-scoring-model:** gets pseudo-labels for the next `bird_detect_v0`.

## Product scenario

A new wildlife image is localized:
- **YOLO finds the bird.** That box is used.
- **YOLO misses and RTMDet finds an animal.** The RTMDet box is used at lower authority.
- **The RTMDet box is under 2% of the frame.** YOLO re-runs on a padded crop around it to tighten
  the box.

Each step's result is stored, so the cascade's choices can be audited and re-evaluated.

## Non-goals

- Insects, reptiles and amphibians. COCO has no classes for them; an open-vocabulary detector
  (OWL-ViT, Grounding DINO, YOLO-World) is a separate benchmark.
- Person detection for people scenes, which belongs to spec 05's routing.
- Writing `images.bird_bbox`, or any production work-selection predicate. This is shadow, per
  rollout stage 4.
- Retraining the YOLO, which belongs in image-scoring-model.

## User stories

- As a scoring developer, I want one authoritative subject box per image with its provenance, so
  that crops are reproducible.
- As an operator, I want false boxes on bird-free frames kept rare, so that subject scores aren't
  corrupted.
- As a model maintainer, I want the fallback detector's tight boxes exported, so that I can
  pseudo-label YOLO training data.

## Acceptance criteria

- **AC-1** — The system shall load RTMDet-tiny weights exported by this repo from the upstream
  OpenMMLab COCO checkpoint.
- **AC-2** — If the RTMDet weights' sha256 does not match the recorded export manifest, then the
  provider shall record `disabled` with error code `weights_mismatch`.
- **AC-3** — The RTMDet provider shall run through `onnxruntime` on the inference rendition,
  letterboxed to 640.
- **AC-4** — The RTMDet provider shall keep boxes of COCO animal classes (`bird`, `cat`, `dog`,
  `horse`, `sheep`, `cow`, `elephant`, `bear`, `zebra`, `giraffe`) and discard `person` and every
  other class.
- **AC-5** — When no animal box reaches confidence 0.4, the RTMDet provider shall retry with a 0.25
  threshold.
- **AC-6** — The RTMDet provider shall persist each kept box with `object_class = animal` and
  `provider_class_id = coco:<class name>`.
- **AC-7** — The cascade provider shall write its own localization run under `detector_key =
  subject_cascade`, with a config hash covering both child providers' config hashes.
- **AC-8** — When the YOLO provider has a current `detected` run, the cascade shall adopt the
  YOLO's ranked boxes with `provider_class_id = yolo:bird`.
- **AC-9** — When the YOLO run is `no_detection` and RTMDet has a current `detected` run, the
  cascade shall adopt the RTMDet boxes.
- **AC-10** — When an adopted RTMDet box covers less than `localization.cascade.refine_area_frac`
  of the frame, the cascade shall run YOLO on a padded crop of that box (crop policy `refine_v1`,
  `pad_frac` 1.0).
- **AC-11** — If the refine pass returns a box with IoU ≥ 0.3 against the RTMDet box, then the
  cascade shall replace the RTMDet box with the refined box mapped back to frame coordinates.
- **AC-12** — The cascade shall record which step produced each adopted region in the run's
  diagnostics: `yolo`, `coco` or `coco+refine`.
- **AC-13** — If both child providers are `no_detection`, then the cascade shall record
  `no_detection`.
- **AC-14** — If either child provider is `retryable_error` and no child has a detection, then the
  cascade shall record `retryable_error`.
- **AC-15** — While `localization.cascade.enabled` is false, the system shall not create
  `subject_cascade` runs.
- **AC-16** — The benchmark script shall report cascade recall and false-positive rate on the #377
  independent strata, with 95% confidence intervals.
- **AC-17** — The benchmark script shall report the LLM-panel TIGHT rate on labelled-bird frames
  for YOLO-640 and for the cascade.
- **AC-18** — The cascade shall not become the default region source for any consumer until its
  independent-strata false-positive rate is ≤ 10% and its recall is ≥ YOLO-640's.

## Assumptions and dependencies

- The localization tables already allow one current run per `(image, detector_key)` (migration 0034
  partial unique index), so no migration is needed.
- `onnxruntime` becomes an optional dependency; see
  [ONNX_CONVERSION_FEASIBILITY.md](../../planning/models/ONNX_CONVERSION_FEASIBILITY.md).
- **Weights provenance:** the research run used ONNX weights from a locally installed third-party
  product. Those weights are **not** used. The export comes from the upstream Apache-2.0 checkpoint
  with a recorded manifest (AC-1, AC-2), and the comparison must be re-run on it before adoption.
- Spec 01 is a soft dependency. Without it, the provider decodes through
  `localization.decode_for_localization`.

## Open questions

Recommendations and deadlines: [07 — decision register](07-blockers-and-decisions.md#3-decision-register) (C-1 to C-4).

1. The refine IoU threshold (0.3) and padding (1.0) are proposals. Sweep them on the cohort.
2. When both YOLO and RTMDet detect, should the cascade keep the RTMDet boxes as extra ranked
   regions (multi-subject), or YOLO only? The proposal is YOLO only for continuity with `bird_bbox`.
3. Is the agreement arm, which accepts YOLO boxes only when RTMDet also sees an animal, worth
   testing as a false-positive filter? It removed 13 of 28 YOLO false positives in `det_*` and kept
   100 of 101 true detections.
4. **The operating point.** At the report's default policy (0.4, retry 0.25), RTMDet's animal arm
   runs 12/71 (17%) false positives on the independent strata, which fails AC-18's 10% gate. Only
   the matched-recall threshold (4%) passes. The threshold in AC-5 may need to rise, or the
   agreement arm from question 3 may be required. The sweep decides which.

## Implementation plan

**Goal:** AC-1 to AC-17 pass in shadow. AC-18 gates any consumer.

**Files:**
- New `modules/detectors/rtmdet.py`: provider, preprocessing, NMS, class filter.
- New `modules/localization_cascade.py`: combination logic, a pure function over child runs.
- `modules/localization.py`: provider registry.
- `modules/localization_runner.py`: run the children, then the cascade.
- New `scripts/models/export_rtmdet_onnx.py`: writes the weights and `manifest.json`.
- `scripts/research/detector_benchmark/run_benchmark.py`: new arms.

**Approach:**
1. Export the weights and manifest.
2. Add the provider with class and threshold policy.
3. Implement cascade selection as a pure function of child runs, with unit tests.
4. Add the refine pass through `crop_cache`.
5. Re-run the benchmark on upstream weights, plus the LLM panel on cascade boxes.

**Tests to write first:**
- `tests/test_rtmdet_provider.py`: AC-2 to AC-6, with a stub ONNX session.
- `tests/test_localization_cascade.py`: AC-7 to AC-15, with every combination of child statuses as
  a pure function.
- `tests/test_detector_benchmark_arms.py`: AC-16 and AC-17 report shape.

**Rollback:** set `localization.cascade.enabled=false` and `localization.detectors.coco.enabled=false`.
Existing runs stay as history.
