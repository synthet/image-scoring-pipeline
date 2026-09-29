---
type: Report
title: Blind owner comparison of bird_detect v0 vs v1 primary boxes
description: Owner A/B preferences on 189 divergent frames from the #377 detector cohort; v1 won 70% of decisive picks, while v0 won most both-detected box comparisons.
resource: docs/reports/bird-detect-v0-v1-blind-compare-2026-09-28.md
tags: [report, localization, bird-detection, benchmark, v0, v1]
timestamp: 2026-09-28T00:00:00Z
okf_version: 0.1
---

# Blind v0 vs v1 box comparison (2026-09-28)

## Context

[`bird_detect_v1.pt`](https://huggingface.co/synthet/bird-detect-v0) is the backend default
(CUB + teacher pseudo-labels fine-tune of v0). Automated benchmarks on the [#377](https://github.com/synthet/image-scoring-pipeline/issues/377)
cohort showed higher recall with controlled false-positive cost ([detector benchmark](detector-benchmark-2026-09.md),
[cascade benchmark addendum](cascade-benchmark-2026-09-27.md)). This study asks:
**when v0 and v1 disagree, which detection output would the owner rather use?**
If one model misses, the choice tests detection availability; if both detect, it compares primary-box quality.

## Method

1. **Cohort:** Same 339-frame stratified library sample as the September 2026 detector benchmark
   (`build_cohort.py`, seed 377). Paths and thumbnails are not committed.
2. **Inference:** Both weights on each frame with the production decode path and `BirdDetector` default
   confidence, input size, and maximum detection count
   (`make_compare_label_page.py infer` → `compare_cache.csv` under gitignored scratch).
3. **Pairs shown:** Only **divergent** frames (one model missed, or both detected with IoU &lt; 0.85
   on normalized primary boxes) — **189** pairs rendered.
4. **Labelling:** Local HTML page with **Option A / Option B** only (no model names). Side assignment
   per image is randomized; mapping lives in gitignored `mapping.json`.
5. **Scoring:** `score_compare_labels.py` joins exported `compare_labels.csv` to `mapping.json` to
   attribute picks to `bird_detect_v0.pt` vs `bird_detect_v1.pt`.

Owner labels and JPEGs remain under `.agent/scratch/bird_detect_compare/` (gitignored). This report
stores **aggregate counts only**.

## Results

All **189** rendered pairs were labelled (complete vs mapping). An independent replay
verified 339 unique cached cohort frames, the exact 189 divergent IDs, all A/B renders,
one label per mapping ID, and the side-to-model assignments. Private input SHA-256 hashes:
labels `61a57009d3973176841696931bee7c44024b5c43a80c1fa2500d458c963c635a`,
mapping `27f87ce99457cf0beaec2c4f2008a970cc683ba27d44d5fe2c27c394ac78fdf9`,
inference cache `c438531a3291d994aa5cf6bd7e5822a945ea80018a164168adc2d20824894808`.

| Pick | Count |
|---|---:|
| Prefer Option A | 88 |
| Prefer Option B | 82 |
| Tie | 5 |
| Neither acceptable | 14 |

**Decisive picks** (chose A or B): **170** frames.

| Preferred model output | Wins | Share of decisive |
|---|---:|---:|
| **bird_detect_v1** | **119** | **70.0%** |
| bird_detect_v0 | 51 | 30.0% |

The aggregate mixes two distinct cases:

| Case | Pairs | Decisive picks | v1 wins | v0 wins | Tie | Neither |
|---|---:|---:|---:|---:|---:|---:|
| One model missed | 115 | 109 | 101 | 8 | 0 | 6 |
| Both detected, boxes diverged | 74 | 61 | 18 | 43 | 5 | 8 |
| **Total** | **189** | **170** | **119** | **51** | **5** | **14** |

Of 91 v1-only-box pairs, the owner chose v1's box 86 times and v0's empty side five times. Of 24
v0-only-box pairs, the owner chose v1's empty side 15 times, v0's box three times, and neither six
times. V1's overall advantage thus combines new detections with rejection of some v0 detections.
**When both detect,
the owner preferred v0's primary box 43 to 18.** In the `det_small` stratum, v0 won 31 of 37
decisive picks. These are useful diagnostics, not estimates for all library images.

## How to read this

- **In scope:** Owner preference on divergent outputs. One-model-missed cases combine detection
  availability and false-alarm judgement; both-detected cases address relative box quality.
- **Out of scope:** Library-wide precision/recall, shadow-rescan promotion ([bird v1 shadow rescan](bird-v1-shadow-rescan-2026-09-28.md)),
  or replacing the human presence labels in [detector-benchmark-2026-09](detector-benchmark-2026-09.md).
- **Bias:** Frames are pre-filtered to disagreement; agreeing frames are not represented. “Neither”
  and “tie” are informative but not scored as v0/v1 wins.
- The inference cache records model filenames and outputs, but not the loaded weights' SHA-256;
  this limits independent reconstruction of the exact inference run.
- The saved aggregate file had said 121 v1 / 49 v0. Re-scoring the complete current private labels
  against the mapping, independently and with the canonical scorer, gives 119 / 51. The input hashes
  above identify the corrected result.

## Reproduce

```powershell
# From repo root (gpu-shell for infer/build)
scripts\batch\docker_gpu_run.bat scripts/research/detector_benchmark/make_compare_label_page.py infer `
  --cohort .agent/scratch/detector_benchmark/cohort.csv `
  --out .agent/scratch/bird_detect_compare

scripts\batch\docker_gpu_run.bat scripts/research/detector_benchmark/make_compare_label_page.py build `
  --cache .agent/scratch/bird_detect_compare/compare_cache.csv `
  --out .agent/scratch/bird_detect_compare/page `
  --only-divergent

scripts\batch\docker_gpu_run.bat scripts/research/detector_benchmark/score_compare_labels.py `
  --labels .agent/scratch/bird_detect_compare/compare_labels.csv `
  --mapping .agent/scratch/bird_detect_compare/page/mapping.json `
  --out .agent/scratch/bird_detect_compare/compare_scores.json
```

Canonical scripts: [`make_compare_label_page.py`](../../scripts/research/detector_benchmark/make_compare_label_page.py),
[`score_compare_labels.py`](../../scripts/research/detector_benchmark/score_compare_labels.py).

## Decision

V1's output is preferred more often in one-model-missed cases, consistent with the automated #377
recall and false-positive evidence. The both-detected and `det_small` slices reveal a box-choice regression to investigate
before treating v1 crops as better. This study alone does **not** justify changing the current default,
bulk `bird_bbox` backfill, or shadow promotion; those decisions require the separate gates in the
shadow rescan report.
