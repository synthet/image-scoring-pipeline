---
type: Plan
title: Bird box agreement plan
description: Implementation plan for spec 08, the shadow per-crop RTMDet check on bird regions.
resource: docs/planning/bird-box-agreement-plan.md
tags: [planning, localization, detection, rtmdet, shadow]
timestamp: 2026-11-03T00:00:00Z
okf_version: 0.2
status: proposed
---

# Bird box agreement plan

**Spec:** [08](../specs/pipeline-streamlining/08-bird-box-agreement.md) · **Issue:** #780

## Goal

Done means every spec 08 acceptance criterion passes, the parity check (AC-9) has a receipt, and the first shadow run has produced the per-shoot report. Nothing in production changes.

## Files

| Path | Change |
|---|---|
| `modules/localization_agreement.py` | New: crop building, agreement score, config hash, run writing |
| `modules/detectors/rtmdet.py` | Read only; use `load_rtmdet` with a low threshold, no retry |
| `modules/localization_agreement_runner.py` | New: stores runs, per-shoot summary |
| `scripts/backfill_bird_agreement.py` | New: backfill and `--report` (AC-7), modelled on `scripts/backfill_region_keypoints.py` |
| `scripts/research/detector_benchmark/agreement_parity.py` | New: AC-9 check against the model repository's calibration predictions |
| `config.example.json` | `localization.agreement`: `enabled` false, `crop_pad` 0.25, `min_iou` 0.3 |
| `tests/test_localization_agreement.py`, `tests/test_backfill_bird_agreement.py` | New |

No migration: `write_run` stores this under the new `bird_agreement` key.

## Approach

1. **Score function, no I/O.** Given a region, a crop box and RTMDet boxes, return the highest bird score with IoU ≥ 0.3 against the region, or 0.0. `iou()` in `modules/localization_cascade.py` is reused.
2. **Provider.** Load RTMDet with `threshold` 0.05 and `retry_threshold` None, and keep boxes where `cls` is `bird`. The 0.60 cascade setting would hide scores near the 0.10 limit. This is a separate provider instance, so the cascade is unaffected.
3. **Parity check (AC-9), before any library run.** If it fails at 95%, stop and revisit the limit. Do not tune it on the test set.
4. **Storage.** One unpublished `bird_agreement` run per image (AC-13). Each region is copied with its source rank and coordinates, `confidence` holds the agreement score, and `provider_class_id` is `agree:region:<region_id>`. A selected region that is not on the current `bird` run is appended after the last rank with `provider_class_id` `agree:selected:<region_id>`.
5. **Backfill.** Decode once, compare rendition hashes (AC-11), skip when unchanged (AC-6), score, write. Failures become `retryable_error` (AC-10). `--dry-run`, `--folder`, `--image-ids` and `--limit` follow the keypoint backfill.
6. **Report (AC-7).** Applies the 0.10 limit at read time (AC-8).
7. **First run.** Keep-one dev and pilot shoots, then the stratified sample.
8. **Promotion review.** Draw the fixed review sample from spec 08's promotion bar and compare with the bar.

## Risks

- **Readers.** Checked: keep-one reads every current run, which is why runs are unpublished (AC-13). Pipeline readers are safe.
- **Selected regions on an older rendition.** Coordinates may not match the decoded pixels. These images are recorded as `retryable_error` under AC-11, not scored.
- **Keep-one input identity.** Unpublished runs stay out of its snapshots, so its receipts do not change.
- **GPU contention.** The run shares the card with other jobs. Run it bounded and resumable.

## Constitution check

Shadow-only, off by default, no production writes, no permission or settings change, no secrets. Calibration and test sets stay unused for tuning.

## Tests

Write these first, in `tests/test_localization_agreement.py`:
- `test_score_is_best_overlapping_bird` (AC-4)
- `test_score_ignores_other_classes_and_low_iou` (AC-4)
- `test_score_is_zero_without_a_match` (AC-4)
- `test_config_hash_covers_inputs` (AC-5)

In `tests/test_backfill_bird_agreement.py`:
- `test_disabled_loads_no_model` (AC-1)
- `test_writes_only_agreement_rows` (AC-2)
- `test_scores_every_region` (AC-3)
- `test_skips_unchanged_image` (AC-6)
- `test_failure_records_retryable_and_continues` (AC-10)
- `test_rendition_mismatch_is_retryable` (AC-11)
- `test_selected_region_is_appended` (AC-12)

The report tests `test_report_counts_and_denominators` (AC-7) and `test_limit_applies_at_read_time` (AC-8) are in the same file.

## Task breakdown

Use `/tasks`: steps 1–3 first, because the parity check can stop the work.

## Rollback

`localization.agreement.enabled` stays false. Rows under `bird_agreement` are ignored by every consumer, and a run can be superseded by a re-run.
