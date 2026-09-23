---
type: Report
title: Detector benchmark — 640 vs 1280 vs tile-on-miss
description: Human-labelled 339-frame stratified benchmark; higher resolution recovers birds but adds many false detections, so production defaults stay unchanged.
resource: reports/detector-benchmark-2026-09.md
tags: [bird_species, localization, detector, benchmark, report]
timestamp: 2026-09-23T00:00:00Z
okf_version: 0.1
---

# Detector benchmark — September 2026

**Issue:** [#377](https://github.com/synthet/image-scoring-backend/issues/377), part of
[#345](https://github.com/synthet/image-scoring-backend/issues/345).
**Status:** evaluation complete, ready for review; production defaults unchanged.

## Decision

Keep `imgsz=640`, `conf=0.25`, and `max_det=10` in production. There is **insufficient
evidence to promote either 1280 or tile-on-miss**. Both recover many birds, but both add
frequent detections on human-labelled bird-free frames. This also does not establish that
640 is adequate for all-image localization: even its sampled positive outputs include false
detections, and the sampling design cannot estimate library-wide error rates.

At 1280, the eagle slice improves from 20/59 to 53/59 detections. On the independent
`miss_birdkw` slice it recovers 56/73 labelled birds. However, in `miss_nokw`, 35/54
verified negatives produce detections at 1280, versus none at 640; tile-on-miss produces
30/54. Tables below give denominators and Wilson 95% intervals for all recall and FP rates.

Stage 3's detector-evaluation deliverable is complete. This supports designing a disabled,
shadow-only stage 4, with false-positive review as an explicit gate. It does **not** approve
changing detector defaults, treating boxes as authoritative, or enabling downstream crops.

## Cohort, labels, and validity

The versioned evidence is [cohort.csv](detector-benchmark-2026-09/cohort.csv),
[labels.csv](detector-benchmark-2026-09/labels.csv),
[results.csv](detector-benchmark-2026-09/results.csv),
[gpu_peak_bytes.csv](detector-benchmark-2026-09/gpu_peak_bytes.csv), and
[manifest.json](detector-benchmark-2026-09/manifest.json). Photo and thumbnail paths are
removed; image and folder IDs retain the local join. No photographs are included.

The [sampler](../../scripts/research/detector_benchmark/build_cohort.py) uses seed 377,
`ORDER BY md5(id || seed)`, NEF sources only, and at most three frames per folder **within
each sampled stratum**. The eagle folder is excluded from those strata. The stored rebuild
is byte-identical to the original cohort. Counts and distinct folders:

| Stratum | Selection | Frames | Folders |
|---|---|---:|---:|
| `det_small` | Stored detection, area fraction < 0.04 | 50 | 28 |
| `det_medium` | Stored detection, area fraction 0.04–<0.15 | 50 | 38 |
| `det_large` | Stored detection, area fraction ≥ 0.15 | 30 | 22 |
| `miss_birdkw` | Stored miss, `birds` keyword | 90 | 54 |
| `miss_nokw` | Stored miss, no `birds` / `wildlife` / `animals` keyword | 60 | 45 |
| `eagle` | Prior 59-frame regression slice | 59 | 1 |

The owner labelled all 280 sampled frames through the local blind page, shuffled with no
detector output or stratum shown, using 1280-pixel thumbnails with zoom: **179 bird,
99 no_bird, 2 unsure**. The 59 eagle frames retain the prior audit's positive labels;
they were not re-labelled in this session. There are no missing, extra, duplicate, or
invalid human labels, and all 339 cohort IDs have exactly one result.

The `a640` arm reproduces stored **detection presence** on 339/339 frames, including
20 detections and 39 misses in the eagle slice. This is not a claim of pixel-exact box
equivalence: the harness uses the new validated `rank_boxes` path, while production's
legacy best-box selection has different malformed-box and tie behavior.

Strata are selected using production output, so `a640` recall on `det_*` is 100% by
construction and its FP rate on negatives there is also 100%. Neither is a population
estimate. No library-wide rate is pooled across strata. Wilson intervals treat frames as
independent; shared folders, and especially one eagle shoot, make them descriptive rather
than a guarantee of generalization. Subject size is the stored box size, not a human box.

## Method and provenance

The [runner](../../scripts/research/detector_benchmark/run_benchmark.py) decodes each frame
once via `open_rendition_for_ml`, RGB conversion, and `bake_orientation`; all arms see the
same pixels. Every frame used `raw_preview`. Median long edge was 6048 pixels: about 9.4×
downscaling at 640 and 4.7× at 1280. Common decoded sizes were 8256×5504 (136), 5392×3592
(73), 6048×4024 (49), 4288×2848 (39), and 3936×2624 (38).

| Arm | Parameters |
|---|---|
| `a640` | Full frame, `imgsz=640`, `conf=0.25`, `max_det=10` |
| `a1280` | Full frame, `imgsz=1280`, same confidence and cap |
| `tile` | Preserve `a640` hits; on a miss, run four overlapping crops at 640, map boxes back, NMS IoU 0.5, then rank and cap at 10 |

For tiling, each crop spans approximately 60% of each frame dimension, with origins at
the two edges. The overlap is 20% of the **full-frame dimension**, approximately one third
of a tile dimension. This clarifies what the runner's `TILE_OVERLAP=0.20` means.

The saved run session records an RTX 4060 Laptop GPU (8 GB), CUDA torch 2.10, and
ultralytics 8.4.120 in `image-scoring-gpu-shell`. Harness commit: `67c68ac`. The detector
loads `synthet/bird-detect-v0` / `bird_detect_v0.pt`. **The original harness did not record
the resolved model revision, weight hash, exact torch build, or a pixel-content hash.**
CSV hashes pin the evidence; exact future inference reproduction additionally requires
recovering and pinning those inputs. Hardware/software details are inherited run records,
not a new environment measurement.

A hit means at least one retained box. Labels measure bird presence only: a box on the
wrong object in a bird-containing frame still receives recall credit. These are therefore
**frame-presence metrics, not localization IoU, mAP, or crop quality**. Unsure labels are
excluded from recall and FP denominators. Small subjects, varied scenes, and the textured
eagle setting are represented, but species and background categories were not annotated;
there is no per-species or per-background performance claim.

## Recall on frames labelled bird

Each cell is hits / labelled positives, percentage, and Wilson 95% interval.

| Stratum | a640 | a1280 | tile |
|---|---|---|---|
| `det_small` | 48/48 = **100%** (93%–100%) | 48/48 = **100%** (93%–100%) | 48/48 = **100%** (93%–100%) |
| `det_medium` | 36/36 = **100%** (90%–100%) | 36/36 = **100%** (90%–100%) | 36/36 = **100%** (90%–100%) |
| `det_large` | 17/17 = **100%** (82%–100%) | 17/17 = **100%** (82%–100%) | 17/17 = **100%** (82%–100%) |
| `miss_birdkw` | 0/73 = **0%** (0%–5%) | 56/73 = **77%** (66%–85%) | 50/73 = **68%** (57%–78%) |
| `miss_nokw` | 0/5 = **0%** (0%–43%) | 3/5 = **60%** (23%–88%) | 4/5 = **80%** (38%–96%) |
| `eagle` | 20/59 = **34%** (23%–47%) | 53/59 = **90%** (80%–95%) | 46/59 = **78%** (66%–87%) |

## False-positive rate on frames labelled no_bird

Each cell is frames with a detection / labelled negatives, percentage, and Wilson 95%
interval. This is not the fraction of detections that are false.

| Stratum | a640 | a1280 | tile |
|---|---|---|---|
| `det_small` | 2/2 = **100%** (34%–100%) | 2/2 = **100%** (34%–100%) | 2/2 = **100%** (34%–100%) |
| `det_medium` | 14/14 = **100%** (78%–100%) | 13/14 = **93%** (69%–99%) | 14/14 = **100%** (78%–100%) |
| `det_large` | 12/12 = **100%** (76%–100%) | 11/12 = **92%** (65%–99%) | 12/12 = **100%** (76%–100%) |
| `miss_birdkw` | 0/17 = **0%** (0%–18%) | 10/17 = **59%** (36%–78%) | 6/17 = **35%** (17%–59%) |
| `miss_nokw` | 0/54 = **0%** (0%–7%) | 35/54 = **65%** (51%–76%) | 30/54 = **56%** (42%–68%) |

At 1280, the 38 detections in `miss_nokw` resolve to **3 bird + 35 no_bird**. The three
baseline detections lost at 1280 are image 1719 (`det_medium`, no_bird), 32617
(`det_large`, no_bird), and 23379 (`det_large`, unsure). The preliminary description
"loses three large birds" was incorrect: none is a confirmed bird regression.

## Label composition

| Stratum | bird | no_bird | unsure | unlabelled |
|---|---:|---:|---:|---:|
| `det_small` | 48 | 2 | 0 | 0 |
| `det_medium` | 36 | 14 | 0 | 0 |
| `det_large` | 17 | 12 | 1 | 0 |
| `miss_birdkw` | 73 | 17 | 0 | 0 |
| `miss_nokw` | 5 | 54 | 1 | 0 |
| `eagle` | 59 | 0 | 0 | 0 |

## Runtime and GPU allocation

| Arm | p50 ms | p95 ms | Peak allocated GPU MiB |
|---|---:|---:|---:|
| `a640` | 146 | 366 | 59 |
| `a1280` | 194 | 388 | 105 |
| `tile` | 310 | 839 | 59 |

Decode is shared and excluded: p50 **507 ms**, p95 **774 ms**. Tile cost includes the
baseline call and the extra pass on 189/339 frames. The reported percentiles use sorted
index `floor(q * (n - 1))`. CUDA is synchronized and both input sizes warmed up before
timing; the fixed arm order and single run do not measure run-to-run timing variance.
Timing includes prediction preprocessing but excludes final `rank_boxes`, the diagnostic
pass, thumbnail writing, and pipeline overhead. GPU figures are PyTorch maximum allocated
bytes, **not** total device use or reserved memory. These are cohort costs, not a measured
production ingestion budget.

## Geometry and multiplicity

| Arm | Frames with any area ≥ 0.90 | Top-box area min / median / max | Retained boxes per frame: frame counts |
|---|---:|---|---|
| `a640` | 2 | 0.020804 / 0.056647 / 0.934441 | 0:189, 1:141, 2:9 |
| `a1280` | 0 | 0.009025 / 0.039339 / 0.360668 | 0:55, 1:200, 2:59, 3:20, 4:4, 6:1 |
| `tile` | 2 | 0.009798 / 0.051311 / 0.934441 | 0:73, 1:208, 2:42, 3:12, 4:4 |

Top-box area summaries exclude zero-detection frames. Both suspicious cases at 640
survive unchanged in the tile arm: image 39367 (`det_large`, no_bird, area 0.934441),
and image 208179 (`eagle`, bird, area 0.931371). A bird label does not verify the oversized
box. There is no evidence here for a universal area ceiling. Only top-box area and a
frame-level any-suspicious flag were stored; a distribution over **all** box areas cannot
be reconstructed. Full box records should be retained in a follow-up.

## Confidence diagnostic and domain gap

Among 117 labelled bird frames missed at 640 (including the separate eagle slice), the
best confidence from a diagnostic 640 call at `conf=0.05` falls into these bands:

| Best confidence | Frames |
|---|---:|
| 0.20–<0.25 | 8 |
| 0.15–<0.20 | 7 |
| 0.10–<0.15 | 17 |
| 0.05–<0.10 | 25 |
| None at or above 0.05 | 60 |

Lowering confidence to 0.20 could only add candidate boxes on eight of these misses;
even 0.05 has no candidate on 60. These counts do not validate the candidate's location
or estimate the corresponding false-positive cost. Lowering confidence alone is not a
supported remedy.

The earlier session's model-data audit reported 1,752 validation boxes, minimum area
0.0597, median 0.31, no negative images, and roughly 300–500-pixel images. That validation
set cannot establish performance on the smaller subjects and bird-free scenes measured
here. Its raw audit is not part of this evidence package, and validation composition alone
does not prove what was present in training. The observed FP/recall tradeoff supports a
follow-up with small-bird boxes, hard negatives, and held-out folders before tuning or
retraining; this cohort must not become both a tuning set and the final promotion test.

## Reproduction and next gate

Recompute the presence metrics without a GPU, database, or photographs:

```sh
python scripts/research/detector_benchmark/score.py --dir docs/reports/detector-benchmark-2026-09
```

This writes `metrics.md` beside the CSVs. The report's recall, FP, label-composition, and
runtime tables are checked against this output. `manifest.json` records SHA-256 hashes
of all four CSVs. To rerun inference, restore private `file_path` values by `image_id` in
a local cohort copy and pin model weights and the full runtime first; the path-free
published cohort alone is sufficient for scoring, not image decoding.

For a later promotion decision, retain every predicted box, review errors at source
resolution, label localization geometry and species/background coverage, and evaluate
on held-out folders. Agree on an acceptable FP rate and end-to-end ingestion budget
before choosing a new default. A shadow localization implementation may proceed with
consumers disabled and explicit detector provenance; production promotion remains gated.

Related: [localization rollout](../architecture/pipeline/localization-rollout.md),
[eagle recall audit](bird-detection-recall-2026-09-07.md), and
[scorer](../../scripts/research/detector_benchmark/score.py).
