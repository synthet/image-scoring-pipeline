---
type: Report
title: Detector cascade benchmark on upstream RTMDet weights (2026-09-27)
description: Spec 03 AC-16 on the #377 cohort with the repo-verified upstream RTMDet-tiny export - operating-point sweep, cascade recall and false positives with Wilson intervals, agreement arm, refine pass; resolves decision C-4 and informs C-3.
resource: docs/reports/cascade-benchmark-2026-09-27.md
tags: [report, localization, detector, cascade, benchmark, rtmdet]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.1
---

# Detector cascade benchmark on upstream RTMDet weights (2026-09-27)

> Spec [03](../specs/pipeline-streamlining/03-detector-cascade.md), #408. Full tables:
> [cascade-benchmark-2026-09-27/cascade_metrics.md](cascade-benchmark-2026-09-27/cascade_metrics.md); per-frame raw
> boxes: `cascade-benchmark-2026-09-27/raw.jsonl`. Script:
> `scripts/research/detector_benchmark/cascade_benchmark.py`.

## Setup

- 339 frames of the #377 cohort, owner labels (`bird` / `no_bird`); presence only, Wilson 95% intervals.
- One decode per frame (the localization decoder, full size), then the production YOLO (`bird_detect_v0`, 640, conf
  0.25) and RTMDet-tiny COCO through onnxruntime on **the image-scoring-model export of the upstream Apache-2.0
  checkpoint**, SHA-256 checked against its manifest (AC-1, AC-2). The research-instrument weights are not used.
- The `independent` strata (`miss_birdkw`, `miss_nokw`) are frames the production detector missed, so YOLO recall
  there is 0 by construction; they measure what the fallback adds. `det_*` are frames it fired on.

## Results

**Independent strata (78 bird, 71 no_bird)**

| COCO policy | cascade recall | cascade false positives |
|---|---|---|
| 0.40, retry 0.25 (spec default) | 92% (84-96%) | **15% (9-26%)**: fails AC-18 |
| **0.40, no retry** | **83% (74-90%)** | **4% (1-12%)**: passes AC-18 |
| 0.50 | 68% (57-77%) | 4% (1-12%) |
| 0.60 | 38% (28-50%) | 0% (0-5%) |

**`det_*` strata (101 bird, 28 no_bird).** YOLO fires on all of them, so the cascade inherits YOLO's 28 false
positives. The agreement arm (keep a YOLO box only if COCO also sees an animal) at the permissive 0.40/0.25 policy
removes **13 of 28** and keeps **100 of 101** true birds, the same numbers the research instrument gave, which
confirms the upstream export reproduces it. At 0.40 without retry it removes 16 of 28 but loses 5 birds.

**Refine pass.** 361 small COCO boxes (< 2% of the frame, conf >= 0.25) were re-run through YOLO on a crop padded
by 1.0 of the box size; 282 (78%) gave a YOLO box with IoU >= 0.3, i.e. would be tightened (AC-10/11).

## Decisions

- **C-4 resolved:** fallback threshold **0.40 without the 0.25 retry**. It passes AC-18 (4% false positives,
  recall 83% vs YOLO's 0% on the same frames). `modules.detectors.rtmdet.DEFAULT_RETRY_THRESHOLD` is `None`.
- **C-3 informed:** the agreement filter works best with its own, permissive threshold (0.25): 13/28 false
  positives removed for 1 lost bird. It is a separate knob from the fallback threshold; slice 2 wires it behind a
  flag.
- These numbers are starting points on 339 frames; re-fit with the labelled-burst set (#415).

## Next

1. Slice 2: persist `coco` and `subject_cascade` runs from the localization runner behind
   `localization.detectors.coco.enabled` / `localization.cascade.enabled` (AC-6, AC-7, AC-15), with the refine pass
   on the inference rendition (spec 01) and the agreement filter as an option.
2. AC-17: grade cascade boxes with the LLM box panel (TIGHT rate) against YOLO-640.
