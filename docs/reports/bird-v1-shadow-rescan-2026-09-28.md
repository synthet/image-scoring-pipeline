---
type: Report
title: Bird detector v1 shadow rescan of legacy no-detection results
description: Complete 35,209-image shadow rescan with bird_detect_v1, owner presence and primary-box labels, and the quality gate before any bird_bbox promotion.
resource: docs/reports/bird-v1-shadow-rescan-2026-09-28.md
tags: [report, localization, bird-detection, shadow, quality]
timestamp: 2026-09-28T00:00:00Z
okf_version: 0.2
---

# Bird detector v1 shadow rescan (2026-09-28)

## Cohort and method

After [`bird_detect_v1.pt` became the backend default](https://github.com/synthet/image-scoring-pipeline/pull/463), the [rescan command](../../scripts/maintenance/shadow_rescan_bird_v1_misses.py) froze 35,209 exact image/run ID pairs. Each had a current `legacy_unversioned` localization `no_detection` run and the exact production `images.bird_bbox = {"detected": false}` sentinel. All source runs came from the same pre-switch legacy import. Because that import did not record the original weights, the cohort is **legacy misses**, not proven v0 outputs.

The rescan used the published v1 weights with SHA-256 `6d09339fb3286c8d10395c29e3b0c14da92d86be5c9d4753c38d4a2ef2e447ba`. It called the existing display-space localization decoder and detector, then wrote current versioned runs and regions. The gitignored snapshot fixed membership; the command rechecked each image's original run ID and production sentinel before inference and skipped the 20 pilot results when resumed. It did not write `bird_bbox`, phase status, species, scores, or keypoints.

## Complete result

| v1 shadow outcome | Images | Share of frozen cohort |
|---|---:|---:|
| Detected at least one box | 16,666 | 47.3% |
| No detection | 18,541 | 52.7% |
| Terminal error: source file missing | 2 | <0.1% |
| **Total** | **35,209** | **100%** |

The final log recorded 16,652 new detections, 18,535 new no-detections, two terminal errors, and 20 already processed pilot images. A post-run database query found 16,666 current v1 `detected` runs, 18,541 `no_detection` runs, and two terminal runs. All 35,209 still had the same production no-bird sentinel. The original 35,209 imported runs remained as non-current history.

For primary v1 boxes, confidence percentiles (10/50/90) were 0.460/0.817/0.906; normalized area percentiles were 0.0027/0.0097/0.0260. Confidence bins contained 1,162 boxes below 0.40, 3,324 from 0.40 to below 0.70, and 12,180 at 0.70 or above. These are detector outputs, not precision or recall measurements; the subsequent owner presence review is below.

## Visual gate

A deterministic local contact sheet sampled four primary boxes in each of nine confidence × box-area bins (36 images). It is stratified for failure discovery, not representative enough to estimate a false-positive rate. It showed clear non-bird boxes on an insect, water texture, horses, and a rabbit; the rabbit example scored 0.86. Several distant or partly hidden subjects were ambiguous at contact-sheet size. The contact sheets remain local and gitignored; no library photos are included in this report.

**Decision:** keep the 16,666 boxes in shadow. Confidence alone cannot safely decide which ones to promote, and no production `bird_bbox` refresh has been run. The independent 339-frame [v1 benchmark](cascade-benchmark-2026-09-27.md) remains the labelled recall/false-positive evidence; its 7% false-positive point should not be inferred for this differently selected library cohort.

## Owner blind presence review

The owner labelled all 216 photos in a local page that hid detector boxes and strata. The export matched the fixed cohort exactly: 216 unique IDs, no missing or invalid labels. The private `labels.csv` has SHA-256 `a3af4d716fc5d91d28efa59cf61a9d98051d3955aff8aefa2cbd66c24b0bc2c7`; the private cohort CSV has SHA-256 `cced499ff6ec48182ff9cec3eed9e0f7c5d6533ed5b55cf19bbf139d87e7c177`. Neither file nor the photos is committed.

For detections, 16 images were sampled in each confidence × normalized box-area cell, with at most one image per folder per cell. Confidence bins are low `[0.25, 0.40)`, mid `[0.40, 0.70)`, and high `[0.70, 1]`; area bins are small `<0.005`, medium `[0.005, 0.02)`, and large `>=0.02`. Another 72 v1 no-detections were sampled at most one per folder. These deliberately balanced counts **are not an image-proportional estimate of library precision**.

| V1 outcome | Confidence | Area | Owner bird | Owner no bird | Unsure |
|---|---|---|---:|---:|---:|
| Detected | High | Small | 14 | 2 | 0 |
| Detected | High | Medium | 9 | 7 | 0 |
| Detected | High | Large | 6 | 10 | 0 |
| Detected | Mid | Small | 7 | 9 | 0 |
| Detected | Mid | Medium | 6 | 10 | 0 |
| Detected | Mid | Large | 3 | 13 | 0 |
| Detected | Low | Small | 5 | 11 | 0 |
| Detected | Low | Medium | 10 | 6 | 0 |
| Detected | Low | Large | 5 | 11 | 0 |
| **Detected sample** | | | **65** | **79** | **0** |
| No detection | | | **11** | **60** | **1** |

The 79 `no_bird` labels on detected photos establish clear false alarms in the sampled cells. Even the most promising predeclared cell (high confidence, small area) has two `no_bird` labels among 16. An exploratory tighter filter (`confidence >= 0.85`, area `< 0.005`) leaves only four reviewed examples, all labelled bird; it is too small and chosen after viewing these labels. Conversely, 11 of the 72 sampled v1 no-detections contain a bird. Presence labels do not verify that a v1 box encloses the bird or is tight enough for a crop.

**Gate remains closed:** no confidence/area rule is supported for production promotion by these labels. A candidate rule needs box-level review and a separate, folder-separated validation sample. `images.bird_bbox` remains unchanged for all 35,209 shadow-rescanned images.

## Owner primary-box review

The owner then judged the **primary v1 box** on all 65 detected photos previously labelled `bird`, using a local page with the whole photo, highlighted box, and enlarged crop. The export matched the frozen image, run, and region IDs exactly: 65 unique rows, no missing or invalid labels. All 144 detected review images still had their current v1 run and the exact production no-bird sentinel. The private box-label CSV has SHA-256 `2da83663ffe040c6a7b0e0ed8511e52bce5269382a71aa3b66c0653a8223b1bf`; neither it nor the photos or IDs is committed.

`Usable` means the primary box contains a bird and frames its visible body usefully. `Poor crop` means a bird is in the box, but it is cut off or framed too loosely. `Wrong target` means no bird is in the box. The 79 detected photos labelled `no_bird` in the blind review cannot have a usable bird box; they are included below as a separate outcome.

| Confidence | Area | Usable | Poor crop | Wrong target | No bird in photo | Unsure |
|---|---|---:|---:|---:|---:|---:|
| High | Small | 6 | 5 | 2 | 2 | 1 |
| High | Medium | 8 | 1 | 0 | 7 | 0 |
| High | Large | 5 | 1 | 0 | 10 | 0 |
| Mid | Small | 0 | 6 | 1 | 9 | 0 |
| Mid | Medium | 0 | 5 | 1 | 10 | 0 |
| Mid | Large | 2 | 1 | 0 | 13 | 0 |
| Low | Small | 0 | 3 | 2 | 11 | 0 |
| Low | Medium | 3 | 5 | 2 | 6 | 0 |
| Low | Large | 5 | 0 | 0 | 11 | 0 |
| **Detected sample** | | **29** | **27** | **8** | **79** | **1** |

Only 29 of the deliberately balanced 144 detected review photos had a usable primary box. This fraction is **not an image-proportional library precision estimate**. The high-confidence, small-area cell had six usable boxes among 16, including two wrong targets on photos that do contain birds. The exploratory tighter cut (`confidence >= 0.85`, area `< 0.005`) has three usable boxes and one unsure among just four reviewed examples. The same development labels cannot validate a cut chosen after inspection.

**Decision:** keep all rescanned boxes in shadow. No confidence/area rule has demonstrated a reliable usable-box yield. Improve or screen the detector/box selection first; only then freeze a candidate rule and assess it on new folder-separated photos with uncertainty. No production promotion or eye-keypoint backfill was started.

## Before promotion

1. Use the presence and box labels as a development set to improve the detector or define an independent box-quality screen. Keep uncertain, non-bird, and unusable boxes in shadow.
2. Freeze any candidate rule before validating it on a new folder-separated sample, measuring box-level precision and recall with uncertainty. Do not choose a threshold and evaluate it on these same 216 labels.
3. If a subset passes, update only those production `bird_bbox` rows still carrying the frozen no-bird sentinel, and compute eye keypoints for the newly current v1 regions before using them. Preserve the versioned shadow and legacy runs for audit.

The rescan implementation and its two selection-guard tests landed in [PR #464](https://github.com/synthet/image-scoring-pipeline/pull/464).

## Follow-ups

- [Owner review replay](bird-v1-owner-review-2026-09-29.md) and [failure review](bird-v1-failure-review-2026-09-30.md):
  causes of the 79 false detections and owner-graded alternative boxes.
- [Promotion gate](bird-v1-promotion-gate-2026-10-01.md) (#469): a frozen RTMDet-bird rule failed
  independent owner validation, so all 16,666 boxes stay in shadow.
- [Scene route benchmark](scene-route-benchmark-2026-10-02.md) (#412): the SigLIP2 bird route filters
  114 of 182 owner-labelled no-bird detections, the false-positive signal a re-gate can use.
