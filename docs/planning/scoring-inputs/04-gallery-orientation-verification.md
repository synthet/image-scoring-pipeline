---
type: Feature Spec
title: Verify gallery orientation and overlay compatibility with corrected scoring inputs
description: Verify gallery orientation and overlay compatibility with corrected scoring inputs
resource: planning/scoring-inputs/04-gallery-orientation-verification.md
tags: [scoring, orientation, tasks]
timestamp: 2026-10-06T04:44:10Z
okf_version: 0.2
---
# Verify gallery orientation and overlay compatibility with corrected scoring inputs

Issue: https://github.com/synthet/image-scoring-gallery/issues/176

Filed checklist: https://github.com/synthet/image-scoring-gallery/issues/176#issuecomment-6009529793

Resumed implementation snapshot, 2026-10-06. Checked items have evidence in [verification](VERIFICATION.md); code remains uncommitted and not deployed. GitHub issues and Project Stage are authoritative.

Behavioral context: derived from competitive analysis of a commercial application's observable behaviour and documentation; contains no code, identifiers, fitted constants or model artefacts from it. Implementation evidence and proposed changes below are from this repository and the gallery repository. Reference preview dimensions and encoding settings are not adopted as requirements.

## Ownership and scope

This is an executable orientation-verification slice of existing gallery issue https://github.com/synthet/image-scoring-gallery/issues/176, not a duplicate issue. Its separate `image_model_scores.input_mode` requirements remain in that issue and are not completed by this checklist. Coordinate with backend [#406](https://github.com/synthet/image-scoring-pipeline/issues/406), [#418](https://github.com/synthet/image-scoring-pipeline/issues/418) and [#568](https://github.com/synthet/image-scoring-pipeline/issues/568).

The gallery already uses EXIF-aware display, RAW preview orientation stamping, and baking for the full viewer. The work verifies compatibility across generated thumbnails, browser/client RAW fallbacks, full preview and detector overlays, correcting only failures reproduced by tests.

## Acceptance criteria

- [ ] GA-AC-1: EXIF 1-8, including reflection, display correctly for legacy tagged thumbnails and new upright thumbnails with absent/normal orientation; no double rotation.
- [x] GA-AC-2: RAW preview extraction preserves source orientation when the embedded JPEG lacks it; browser fallback and full viewer produce the same upright framing, while preserving available preview detail.
- [ ] GA-AC-3: Grid/viewer preserve aspect ratio under contain sizing. Boxes and keypoints are mapped using their declared oriented rendition dimensions and provenance, excluding surrounding padding. Existing backend coordinate schema is retained; no blanket conversion to normalized coordinates is assumed.
- [ ] GA-AC-4: An asymmetric fixture and representative real portrait/landscape samples agree with the backend's corrected scoring orientation. Scene label "portrait" and head-facing direction never drive EXIF rotation.

## Ordered implementation tasks

- [ ] GA-T-1: Extend `src/utils/exportImageBake.test.ts`, `src/utils/nefViewer.test.ts` and `electron/nefExtractor.test.ts` for source-tag fallback, EXIF reflection and once-only rotation (GA-AC-1/2).
- [ ] GA-T-2: Add focused grid/viewer/overlay regression coverage with distinct corner and subject landmarks; compare tagged versus baked variants at identical display dimensions (GA-AC-1/3/4).
- [ ] GA-T-3: Make a minimal gallery fix only for a reproduced compatibility failure. Keep protocol/path loading and scoring backend ownership explicit (GA-AC-1..4).
- [ ] GA-T-4: Run focused Vitest tests, renderer/Electron type checks and visual grid/full-view/overlay inspection alongside backend sample evidence. Attach results to gallery #176 without closing its unrelated score-reader work (GA-AC-1..4).

## Rollout and rollback

Support both legacy tagged and newly baked thumbnails during transition. Coordinate cache refresh with backend #406. No independent gallery-wide thumbnail rewrite is required by this verification slice.

## Published baseline reconciliation

The display/export fix is already published in gallery 63e7b2c, with its [solution and recorded verification](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/05-jpeg-export-exif-orientation.md). Reuse the 56 recorded tests, numeric extraction, RAW source-tag fallback and once-only export behavior; those tests were reviewed, not rerun in this backend session. Corrected backend scoring previews for DSC_9144 and DSC_5416 match the recorded upright framing. Full tagged/baked thumbnail, asymmetric grid/viewer and declared-rendition overlay coverage remains open, together with RAW thumbnail handling under #406/#418. Gallery #176's separate score input-mode reader requirements remain open.
