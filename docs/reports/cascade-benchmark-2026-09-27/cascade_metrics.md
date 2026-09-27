---
type: Report
title: Cascade benchmark tables (2026-09-27)
description: Generated tables from scripts/research/detector_benchmark/cascade_benchmark.py; see the parent report for reading.
resource: docs/reports/cascade-benchmark-2026-09-27/cascade_metrics.md
tags: [report, localization, detector, cascade, generated]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.1
---

# Cascade benchmark (#408, spec 03 AC-16)

Frames: 339 of the #377 cohort; labels from `labels.csv` (owner). Presence only: a frame counts as detected when the arm returns at least one box. Wilson 95% intervals. `agree@t` keeps a YOLO box only when COCO also sees an animal at t, and otherwise falls back to COCO at t, so its presence equals `coco@t`.

## independent (78 bird, 71 no_bird)

| arm | recall (bird) | false positives (no_bird) |
|---|---|---|
| yolo | 0/78 (0%, 0%-5%) | 0/71 (0%, 0%-5%) |
| coco@0.40/0.25 | 72/78 (92%, 84%-96%) | 11/71 (15%, 9%-26%) |
| cascade@0.40/0.25 | 72/78 (92%, 84%-96%) | 11/71 (15%, 9%-26%) |
| coco@0.40 | 65/78 (83%, 74%-90%) | 3/71 (4%, 1%-12%) |
| cascade@0.40 | 65/78 (83%, 74%-90%) | 3/71 (4%, 1%-12%) |
| coco@0.50 | 53/78 (68%, 57%-77%) | 3/71 (4%, 1%-12%) |
| cascade@0.50 | 53/78 (68%, 57%-77%) | 3/71 (4%, 1%-12%) |
| coco@0.60 | 30/78 (38%, 28%-50%) | 0/71 (0%, 0%-5%) |
| cascade@0.60 | 30/78 (38%, 28%-50%) | 0/71 (0%, 0%-5%) |
| coco@0.70 | 14/78 (18%, 11%-28%) | 0/71 (0%, 0%-5%) |
| cascade@0.70 | 14/78 (18%, 11%-28%) | 0/71 (0%, 0%-5%) |

## det_* (101 bird, 28 no_bird)

| arm | recall (bird) | false positives (no_bird) |
|---|---|---|
| yolo | 101/101 (100%, 96%-100%) | 28/28 (100%, 88%-100%) |
| coco@0.40/0.25 | 100/101 (99%, 95%-100%) | 15/28 (54%, 36%-70%) |
| cascade@0.40/0.25 | 101/101 (100%, 96%-100%) | 28/28 (100%, 88%-100%) |
| coco@0.40 | 96/101 (95%, 89%-98%) | 12/28 (43%, 27%-61%) |
| cascade@0.40 | 101/101 (100%, 96%-100%) | 28/28 (100%, 88%-100%) |
| coco@0.50 | 87/101 (86%, 78%-92%) | 8/28 (29%, 15%-47%) |
| cascade@0.50 | 101/101 (100%, 96%-100%) | 28/28 (100%, 88%-100%) |
| coco@0.60 | 76/101 (75%, 66%-83%) | 6/28 (21%, 10%-40%) |
| cascade@0.60 | 101/101 (100%, 96%-100%) | 28/28 (100%, 88%-100%) |
| coco@0.70 | 48/101 (48%, 38%-57%) | 1/28 (4%, 1%-18%) |
| cascade@0.70 | 101/101 (100%, 96%-100%) | 28/28 (100%, 88%-100%) |

## eagle (0 bird, 0 no_bird)

| arm | recall (bird) | false positives (no_bird) |
|---|---|---|
| yolo | - | - |
| coco@0.40/0.25 | - | - |
| cascade@0.40/0.25 | - | - |
| coco@0.40 | - | - |
| cascade@0.40 | - | - |
| coco@0.50 | - | - |
| cascade@0.50 | - | - |
| coco@0.60 | - | - |
| cascade@0.60 | - | - |
| coco@0.70 | - | - |
| cascade@0.70 | - | - |

## Refine pass

Small COCO boxes (< 2% of frame, conf >= 0.25) re-run through YOLO on a crop: 361; refined (IoU >= 0.3): 282.

