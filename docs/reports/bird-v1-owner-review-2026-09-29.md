---
type: Report
title: Bird detector v1 shadow-rescan owner review
description: Blind presence and primary-box review of a folder-balanced, stratified development sample from the 35,209-image v1 shadow rescan; production promotion remains blocked.
resource: reports/bird-v1-owner-review-2026-09-29.md
tags: [report, localization, bird-detection, shadow, owner-labels, quality]
timestamp: 2026-09-29T00:00:00Z
okf_version: 0.2
---

# Bird detector v1 shadow-rescan owner review (2026-09-29)

## Scope and method

The [v1 shadow rescan](bird-v1-shadow-rescan-2026-09-28.md) produced 16,666 candidate
detected runs and 18,541 no-detection runs from frozen legacy misses. This review sampled
16 detected frames from each of nine confidence × normalized-area cells (144 total), plus
72 no-detection frames. Selection was deterministic, with at most one image per folder in
each cell. The owner first labelled **bird / no bird / unsure** on photos without boxes or
detector metadata, then graded the v1 primary box on each detected frame labelled bird as
**usable / poor crop / wrong target / unsure**. All 216 presence labels and all 65 applicable
box labels are complete. The box export was checked against frozen run and region IDs.

The cohort, labels, photos and box manifest are private and gitignored under
`.agent/scratch/bird_v1_owner_labels/`. The tracked
[`analyze_v1_owner_review.py`](../../scripts/research/detector_benchmark/analyze_v1_owner_review.py)
replays the aggregate counts from those inputs without a database. Input SHA-256 values:

| Private input | SHA-256 |
|---|---|
| `cohort.csv` | `cced499ff6ec48182ff9cec3eed9e0f7c5d6533ed5b55cf19bbf139d87e7c177` |
| `labels.csv` | `a3af4d716fc5d91d28efa59cf61a9d98051d3955aff8aefa2cbd66c24b0bc2c7` |
| `sampling.json` | `ef14f2eb3cc0dda49d06932f4dec06ed3fd96e48d7e8aac4b34fa82b27c0c785` |
| `box_page/box_labels.csv` | `2da83663ffe040c6a7b0e0ed8511e52bce5269382a71aa3b66c0653a8223b1bf` |
| `box_page/manifest.json` | `16e600e5cd8dc6c2bb5d023667fc020aa3b074e52d6b8dc1b61103f272cbb18b` |

## Results

| Shadow outcome in review | Bird visible | No bird visible | Unsure | Total |
|---|---:|---:|---:|---:|
| v1 detected | 65 | 79 | 0 | 144 |
| v1 no detection | 11 | 60 | 1 | 72 |

The primary-box review on the 65 bird-visible, v1-detected frames found **29 usable**, **27
poor crops**, **8 wrong targets**, and **1 unsure**. Thus only 29 of the 144 reviewed
detected frames had a confirmed usable primary bird crop. The high-confidence cells
(confidence ≥ 0.70) still contained 19 no-bird frames out of 48 reviewed; 19 of those
48 had a usable primary box. Confidence alone is insufficient to select safe promotions.

The exploratory confidence ≥ 0.80 and area < 0.005 cut contained ten reviewed frames:
six usable, one poor crop, one wrong target, one no-bird frame, and one unsure. That cut
was considered **after** inspecting these labels and cannot validate itself. Secondary
v1 regions existed on 11 of the 35 bird-visible frames whose primary box was poor or
wrong, but those alternative boxes were not graded. A read-only v0 probe on these 144
frames missed all 29 v1 frames with usable primary boxes; the original imported legacy
misses do not establish that v0 produced the historical results.

These counts describe a deliberately stratified, folder-balanced **development sample**.
The raw fractions are not estimates of library-wide precision, recall or box usability.
The sample contains only 16 frames per detected cell, does not stratify by scene type,
and supplied the exploratory threshold cuts. A separate frozen validation sample is
required for any proposed promotion rule.

## Decision and next work

**Do not promote the 16,666 shadow boxes to `images.bird_bbox`.** The owner review finds
both false detections and poor primary crops, including high-confidence failures. There
is no validated subset or promotion rule. Production `bird_bbox` remains the frozen
no-bird sentinel in the post-rescan check; this review made no production database
changes. The versioned shadow runs remain available for diagnostics and model improvement.

Investigate the missed birds and box-choice failures, including whether a secondary
region or cascade provider gives a better crop. Define a rule on development data, then
test it on a newly frozen, independently labelled sample with enough cases in each
proposed promotion stratum to estimate both bird presence and primary-box usability.
Only after that gate passes should a guarded subset promotion and eye-keypoint refresh
be considered.

Replay locally:

```powershell
python scripts/research/detector_benchmark/analyze_v1_owner_review.py `
  .agent/scratch/bird_v1_owner_labels
```

## Diagnostic failure-review page

The local, gitignored `failure_review/index.html` under the same scratch directory shows
the 79 no-bird detections and 35 poor or wrong primary boxes alongside ranked v1
regions, RTMDet animal boxes, and small-box YOLO refinements. The page saves case
reviews in browser storage and exports `failure_review.csv`. Its RTMDet and refine
candidates were inferred from the already rendered **review JPEGs**, so they are for
qualitative diagnosis, not a production-rendition benchmark or promotion decision.

[`build_v1_failure_review.py`](../../scripts/research/detector_benchmark/build_v1_failure_review.py)
recreates the page from the frozen private inputs. Run its `prepare`, `probe`, then
`build` actions in the GPU shell. The `probe` action requires the optional
`onnxruntime` package and the verified RTMDet ONNX weights.

The owner completed this diagnostic page on 2026-09-30. The
[failure-review report](bird-v1-failure-review-2026-09-30.md) replays all 114
case labels, grades the alternative boxes, and records why those results do
not yet permit production promotion.
