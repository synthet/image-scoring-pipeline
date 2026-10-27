---
type: Feature Spec
title: Fix EXIF orientation before quality-scoring preprocessing
description: Fix EXIF orientation before quality-scoring preprocessing
resource: planning/scoring-inputs/01-scoring-orientation.md
tags: [scoring, orientation, tasks]
timestamp: 2026-10-06T04:44:10Z
okf_version: 0.2
---
# Fix EXIF orientation before quality-scoring preprocessing

Issue: https://github.com/synthet/image-scoring-pipeline/issues/568

Resumed implementation snapshot, 2026-10-06. Checked items have evidence in [verification](VERIFICATION.md); code remains uncommitted and not deployed. GitHub issues and Project Stage are authoritative.

Behavioral context: derived from competitive analysis of a commercial application's observable behaviour and documentation; contains no code, identifiers, fitted constants or model artefacts from it. Implementation evidence and proposed changes below are from this repository and the gallery repository. Reference preview dimensions and encoding settings are not adopted as requirements.

## Problem and evidence

The quality-scoring pipeline can score a sideways image while the gallery displays it upright. `PrepWorker` converts RAWs to a temporary JPEG; `ScoringWorker` then calls the backend preprocessor. In `scripts/python/run_all_musiq_models.py`, raster loading uses `Image.open(...).convert("RGB")`, and embedded-preview extraction does not apply the original RAW orientation before resize/pad/save. The rawpy route can already return upright pixels.

A synthetic Pillow probe in gpu-shell reproduced the transformation gap: stored 600x400 pixels with EXIF orientation 6 resize to 512x341 without normalization, versus 341x512 after normalization. This is preprocessing evidence, not a real-model score-impact measurement. All eight EXIF values, including mirrored cases, require coverage.

## Scope and dependencies

This task owns the quality-scoring original/temporary-JPEG path. Shared decode and thumbnail generation remain under https://github.com/synthet/image-scoring-pipeline/issues/406; thumbnail consumers and embedding refresh remain under https://github.com/synthet/image-scoring-pipeline/issues/418. Coordinate gallery verification with https://github.com/synthet/image-scoring-gallery/issues/176. Do not wait for full shared-cache adoption to correct scoring orientation.

Keep existing scoring resolution, black-padding policy, RAW decoder preference and model weights for the initial fix. Preserve source files. Camera framing/EXIF orientation is distinct from the semantic scene label "portrait" and from subject head-facing direction.

## Acceptance criteria

- [x] OR-AC-1: Every supported EXIF orientation is applied before scoring resize/pad/crop; asymmetric pixel landmarks validate rotation and reflection, not only width/height.
- [x] OR-AC-2: Embedded previews missing usable orientation fall back to the original source metadata; already-oriented rawpy output is not rotated again. Missing/invalid metadata follows a documented deterministic fallback.
- [x] OR-AC-3: Intermediate scoring JPEGs contain upright pixels and absent/normal orientation metadata. Repeated preprocessing is orientation-idempotent; portrait/landscape proportions and configured padding are preserved.
- [x] OR-AC-4: Cache identity includes a preprocessing policy version and relevant transform settings; pre-fix cached inputs cannot be returned under the corrected policy. Bump the scoring executor version and document rerun eligibility.
- [ ] OR-AC-5: A representative JPEG/RAW sample agrees with gallery display orientation. Include available HE/HE* samples and decoder fallbacks. Record score/ranking changes without claiming rotation-invariant model scores.
- [x] OR-AC-6: Produce an affected-image selection and bounded rescoring procedure; existing scores are not silently mixed with corrected-policy results. No automatic full-library rescore as part of rollout.
- [x] OR-AC-7: Keep source EXIF/storage dimensions distinct from upright rendition dimensions and any padded model canvas. Derive portrait/landscape from upright width/height; a natively portrait image with EXIF 1 remains portrait. Rotation/reflection is not inferred from scene or head-facing labels.

## Ordered implementation tasks

- [x] OR-T-1: Re-check current worktree and reproduce through actual scoring entrypoints; existing uncommitted thumbnail work must be preserved.
- [x] OR-T-2: Add failing tests in `tests/test_scoring_orientation.py`: `test_scoring_applies_all_exif_transforms`, `test_raw_preview_uses_source_orientation`, `test_rawpy_output_is_not_rotated_twice`, `test_missing_orientation_has_deterministic_fallback` (OR-AC-1/2).
- [x] OR-T-3: Carry original source and decode-route provenance through RAW conversion; reuse/factor our orientation helpers without changing the decoding policy. Normalize before intermediate saves in `scripts/python/run_all_musiq_models.py` and `modules/pipeline.py` (OR-AC-1/2/3).
- [x] OR-T-4: Add `test_prepared_input_is_upright_and_idempotent` and `test_orientation_policy_invalidates_old_cache`; version preprocessing and `modules/phases.py` scoring executor (OR-AC-3/4).
- [ ] OR-T-5: Coordinate the RAW-thumbnail double-rotation regression with #406/#418: rawpy may rotate pixels before `generate_thumbnail` copies source Orientation. Extend `tests/test_thumbnail_orientation.py` under that ownership (OR-AC-5).
- [ ] OR-T-6: Run focused pytest in gpu-shell, then sample model inference and gallery grid/viewer checks. Publish evidence and a targeted rerun/rollback procedure (OR-AC-5/6).
- [x] OR-T-7: Add `test_source_and_display_dimensions_are_distinct` and `test_native_portrait_orientation_one_is_preserved`; verify descriptor dimensions after EXIF 5-8 and a native portrait EXIF-1 image (OR-AC-7).

## Rollout and rollback

Ship orientation correction independently of input-routing and resize-policy changes. Use new cache keys rather than deleting unrelated caches. Preserve old score provenance and record the policy on new runs. Rollback is a scoped code revert plus an explicit compatible policy version; never relabel old inputs as corrected.

## Implementation evidence

See [verification and bounded rollout](VERIFICATION.md) and the updated [canonical model-input contract](../../technical/MODEL_INPUT_SPECIFICATIONS.md). All 265 focused backend tests passed in gpu-shell. Real model score measurements and same-machine HTTP equivalence are recorded separately from the reviewed gallery baseline. Production resize/padding/decoder defaults remain unchanged. Remaining unchecked work retains its original ownership and does not imply deployment completion.
