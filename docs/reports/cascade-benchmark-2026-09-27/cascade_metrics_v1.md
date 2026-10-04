---
type: Report
title: Cascade benchmark tables with bird_detect_v1 (2026-09-27)
description: Generated tables from scripts/research/detector_benchmark/cascade_benchmark.py with bird_detect_v1 as the first stage; see the parent report for reading.
resource: docs/reports/cascade-benchmark-2026-09-27/cascade_metrics_v1.md
tags: [report, localization, detector, cascade, generated]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.2
---

# Cascade benchmark (#408, spec 03 AC-16)

Frames: 339 of the #377 cohort; labels from `labels.csv` (owner). Presence only: a frame counts as detected when the arm returns at least one box. Wilson 95% intervals. `agree@t` keeps a YOLO box only when COCO also sees an animal at t, and otherwise falls back to COCO at t, so its presence equals `coco@t`.

## independent (78 bird, 71 no_bird)

| arm | recall (bird) | false positives (no_bird) |
|---|---|---|
| yolo | 63/78 (81%, 71%-88%) | 5/71 (7%, 3%-15%) |
| coco@0.40/0.25 | 72/78 (92%, 84%-96%) | 11/71 (15%, 9%-26%) |
| cascade@0.40/0.25 | 74/78 (95%, 88%-98%) | 14/71 (20%, 12%-30%) |
| coco@0.40 | 65/78 (83%, 74%-90%) | 3/71 (4%, 1%-12%) |
| cascade@0.40 | 71/78 (91%, 83%-96%) | 7/71 (10%, 5%-19%) |
| coco@0.50 | 53/78 (68%, 57%-77%) | 3/71 (4%, 1%-12%) |
| cascade@0.50 | 69/78 (88%, 80%-94%) | 7/71 (10%, 5%-19%) |
| coco@0.60 | 30/78 (38%, 28%-50%) | 0/71 (0%, 0%-5%) |
| cascade@0.60 | 65/78 (83%, 74%-90%) | 5/71 (7%, 3%-15%) |
| coco@0.70 | 14/78 (18%, 11%-28%) | 0/71 (0%, 0%-5%) |
| cascade@0.70 | 64/78 (82%, 72%-89%) | 5/71 (7%, 3%-15%) |

## det_* (101 bird, 28 no_bird)

| arm | recall (bird) | false positives (no_bird) |
|---|---|---|
| yolo | 99/101 (98%, 93%-99%) | 14/28 (50%, 33%-67%) |
| coco@0.40/0.25 | 100/101 (99%, 95%-100%) | 15/28 (54%, 36%-70%) |
| cascade@0.40/0.25 | 101/101 (100%, 96%-100%) | 18/28 (64%, 46%-79%) |
| coco@0.40 | 96/101 (95%, 89%-98%) | 12/28 (43%, 27%-61%) |
| cascade@0.40 | 101/101 (100%, 96%-100%) | 16/28 (57%, 39%-73%) |
| coco@0.50 | 87/101 (86%, 78%-92%) | 8/28 (29%, 15%-47%) |
| cascade@0.50 | 100/101 (99%, 95%-100%) | 15/28 (54%, 36%-70%) |
| coco@0.60 | 76/101 (75%, 66%-83%) | 6/28 (21%, 10%-40%) |
| cascade@0.60 | 99/101 (98%, 93%-99%) | 15/28 (54%, 36%-70%) |
| coco@0.70 | 48/101 (48%, 38%-57%) | 1/28 (4%, 1%-18%) |
| cascade@0.70 | 99/101 (98%, 93%-99%) | 14/28 (50%, 33%-67%) |

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

Small COCO boxes (< 2% of frame, conf >= 0.25) re-run through YOLO on a crop: 361; refined (IoU >= 0.3): 263.

