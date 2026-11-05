---
type: Feature Spec
title: "Spec 08: bird box agreement"
description: A shadow check that asks RTMDet to confirm each bird_detect_v1 region on its padded crop, to measure how many false eyes on detector false positives it would remove.
resource: docs/specs/pipeline-streamlining/08-bird-box-agreement.md
tags: [specs, localization, detection, keypoints, rtmdet, shadow]
timestamp: 2026-11-03T00:00:00Z
okf_version: 0.2
status: done
---

# Spec 08: bird box agreement

**Issue:** #780 · **Hub:** [INDEX.md](INDEX.md) · **Depends on:** spec 03, #426

## Outcome

Finished on 2026-11-05 and **the promotion bar was not met**: 12.0% of false-eye regions removed (bar: at least a third) and 2.6% of confirmed birds lost (bar: under 2%). No promotion spec follows, the second run is dropped, and agreement stays a shadow measurement. Rates are weighted to the pool, because the sample took 100 regions from each side of the limit. Details are on #780.

## Summary

The eyes the fleet stores come from `bird_detect_v1` regions, so a false box can produce a false eye. Many false boxes hold real animals, so raising the consumer eye floor does not remove those eyes (#779 kept it at 0.8).

The model repository's eye benchmark tested a second detector as a filter: one untiled RTMDet pass per padded box crop, keeping a box when RTMDet sees an overlapping bird at agreement ≥ 0.10. Results for no-subject frames with a false eye:

| Labelled set | Fleet path | With the check | Difference [95% CI] |
|---|---|---|---|
| Calibration | 0.56 | 0.26 | −0.31 [−0.43, −0.20] |
| Test (21 no-subject frames) | 0.19 | 0.10 | −0.10 [−0.30, 0.09] |
| Confirmation | 0.43 | 0.14 | −0.29 [−0.40, −0.17] |

Eyes within 5% did not fall on any set, and one bird was lost on one set. The check costs about 2× the eye path (about 200 ms against 105 ms). Source: image-scoring-model `docs/reports/eye-model-benchmark-2026-11-03.md`.

This spec records the same check for real library images, in shadow. Nothing reads it for selection, scoring or display.

## Users / stakeholders

- **Owner:** decides from per-shoot numbers whether the check is worth promoting.
- **Keep-one (skills):** its eye signals read stored eyes, so a later promotion would affect it.
- **Gallery:** shows stored eyes; unaffected until a promotion.

## Product scenario

After a shadow run on chosen shoots, the owner can see for each shoot how many stored bird regions RTMDet confirms, how many it does not, and how many stored eyes sit on unconfirmed regions. That is enough to decide on a promotion spec. Today this exists only as a benchmark on three labelled samples.

## Non-goals

- Changing region selection, `images.bird_bbox`, scores, keywords, phase status or stored keypoints.
- Changing `EYE_CONSUMER_MIN_CONF` or any consumer.
- Tiled RTMDet, which costs about 6× for a small extra gain.
- Making the cascade a region source (spec 03 AC-18 keeps its own gate).
- Running as a pipeline phase. This is a backfill, like `scripts/backfill_region_keypoints.py`.
- Removing the remaining false eyes: 0.05–0.26 of no-subject frames still get one.

## User stories

- As the owner, I want per-shoot agreement numbers so that I can decide on promotion from my own library, not only from a labelled sample. (AC-3, AC-4, AC-7, AC-8, AC-12)
- As a pipeline maintainer, I want the result stored with its provider identity so that a re-run or a changed model is detectable. (AC-5, AC-6)
- As a consumer owner, I want nothing to change until a promotion decision so that shadow runs are safe. (AC-1, AC-2, AC-10, AC-11, AC-13)
- As a reviewer, I want proof that the pipeline's RTMDet behaves like the benchmark's so that the measured results apply. (AC-9)

## Acceptance criteria

- **AC-1:** While `localization.agreement.enabled` is false, the pipeline shall not load RTMDet for this check.
- **AC-2:** The agreement backfill shall write only `image_localization_runs` and `image_regions` rows for detector key `bird_agreement`.
- **AC-3:** When the backfill processes an image with a current `detected` `bird` run, the system shall record one agreement score for each region of that run.
- **AC-4:** The agreement score for a region shall be the highest RTMDet bird score among boxes found on that region's crop, padded by 25%, whose IoU with the region is at least 0.3, and 0.0 when there are none.
- **AC-5:** The `bird_agreement` run shall store a detector config hash that covers the RTMDet weights hash, crop padding, IoU limit and the `bird` run's detector config hash.
- **AC-6:** When the newest `bird_agreement` run for an image, unless it is a `retryable_error`, has the same config hash, rendition hash and source hash, the backfill shall skip that image.
- **AC-7:** The report script shall print, per shoot, the counts of regions, regions at or above the agreement limit, regions below it, and consumer-visible eyes on regions below it, with their denominators.
- **AC-8:** The agreement limit of 0.10 shall apply only in the report, so that stored scores stay valid if the limit changes.
- **AC-9:** Before the first library run, a parity check shall show the pipeline's ONNX RTMDet and the benchmark's RTMDet giving the same pass or fail at the 0.10 limit on at least 95% of the regions in the model repository's calibration sample.
- **AC-10:** If RTMDet fails on an image, then the backfill shall record a `retryable_error` run for that image and continue with the next one.
- **AC-11:** If the decoded rendition hash differs from the `bird` run's rendition hash, then the backfill shall record a `retryable_error` run for that image.
- **AC-12:** When an image has an active production selection, the backfill shall also record an agreement score for the selected region.
- **AC-13:** The backfill shall store every `bird_agreement` run with `is_current` false.

## Assumptions and dependencies

- `write_run` can store this under a new `detector_key` with no migration.
- **Readers do not all filter on `detector_key`.** Keep-one's `subject_snapshot` takes every current run of an image, and `subject_evidence` requires exactly one detected run, so a current `bird_agreement` run would make those frames ambiguous and trip its input-identity check. AC-13 avoids this with `write_run(publish=False)`: the newest attempt per image is the live one. Pipeline readers were checked; those without a detector filter are a counter, a log line and a script that reaches regions through keypoint runs.
- **Agreement is not available today.** The cascade adopts YOLO's boxes on a `detected` run and does not run RTMDet there, so this is a new pass.
- **The two RTMDet paths differ.** The benchmark uses the PyTorch model with no score threshold and the bird class only. `modules/detectors/rtmdet.py` is ONNX, filters to animal classes and defaults to a 0.60 threshold, which would hide every score near 0.10. The check needs its own low threshold and the raw bird score, which is why AC-9 exists.
- Coordinates: regions are normalised to the display rendition. The benchmark used 2048 px renditions; `/plan` should confirm the crop source matches.
- The model repository's calibration data is local to that repository, so AC-9 is a local check, not CI.

## Decisions

Recorded 2026-11-03: owner, delegated to Jev (jev-1.14.0).

- **Regions:** check every region of the `bird` run, as the benchmark did (p 0.74). This shows whether another box was the real bird.
- **Selected regions:** also score the region of an active production selection, because that is what consumers read (p 0.85). See AC-12.
- **First run:** the keep-one dev and pilot shoots, then a stratified sample across camera and lens as a second run (0.73). The keep-one shoots show the effect on the most exposed consumer, but they over-represent long-lens bird shoots, so the first run alone does not predict the whole library.

Recorded 2026-11-03: owner go-ahead on the suggested bar.

- **Promotion bar, set before any shadow results:** a promotion spec is justified if false-eye regions fall by at least a third and fewer than 2% of confirmed birds are lost. Measure both on a fixed random sample drawn before review: 100 regions below the limit and 100 at or above it, with the owner judging each as bird or not and each stored eye as real or false.
- **Selected-region storage:** in the `bird_agreement` run, appended after the last rank with `provider_class_id` `agree:selected:<region_id>`. No migration.

Implementation plan: [bird-box-agreement-plan.md](../../planning/bird-box-agreement-plan.md).
