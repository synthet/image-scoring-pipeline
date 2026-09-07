---
type: Report
title: Bird detection recall floor — A41 eagle set
description: YOLO bird detection missed 39 of 59 frames on a bald-eagle shoot; the driver is subject size at imgsz=640, with an effective recall floor near area_frac 0.04.
resource: reports/bird-detection-recall-2026-09-07.md
tags: [bird_species, bird_bbox, detector, recall, report]
timestamp: 2026-09-07T20:48:01Z
okf_version: 0.1
---
# Bird detection recall floor — A41 eagle set

**Date:** 2026-09-07 · **Type:** point-in-time audit, one folder · **Status:** finding, no code change made

While running a crop-scoring pipeline over `D:\Photos\Export\2026\A41` (59 frames, one bald
eagle, NIKON Z 8 + 180-600 mm, shot 2026-08-23), the `bird_species` detector was found to have
**missed the bird in 39 of 59 frames** — every one of which visibly contains a large, unobscured
bald eagle. The rows are not `NULL` and carry no `error`: they are
`{"detected": false}`, meaning YOLO ran and returned nothing.

This is a recall problem, not a localisation problem. Where the detector *did* fire, the box was
accurate (see [Box accuracy](#box-accuracy)).

## Evidence

All 59 export JPEGs resolve to indexed rows under
`/mnt/d/Photos/Z8/180-600mm/2026/2026-08-23`. State counts:

| `images.bird_bbox` state | Count |
|--------------------------|-------|
| xyxy object (real box) | **20** |
| `{"detected": false}` | **39** |
| `NULL` (never scanned) | 0 |
| `{"detected": false, "error": ...}` | 0 |

Every one of the 39 misses was hand-boxed by a vision model to measure the subject. Comparing
detector `area_frac` against those hand-measured areas:

| Group | n | min `area_frac` | median | max |
|-------|---|-----------------|--------|-----|
| Detected | 20 | 0.0405 | **0.0590** | 0.9314 |
| Missed (hand-measured) | 39 | 0.0117 | **0.0140** | 0.0478 |

The two populations separate almost cleanly at **`area_frac` ≈ 0.04**:

- smallest detected: `DSC_2184` at 0.0405
- largest missed: `DSC_2198` and `DSC_2191` at 0.0478

Only three frames sit in the overlap. Median subject area differs by **4.2×**.

## Mechanism — `imgsz=640` on a 5392 px decode

`modules/bird_detection.py` runs `predict(conf=0.25, max_det=10)` at **`imgsz=640`**
(`_DEFAULT_IMGSZ`). The decode these frames were scanned at is **5392 × 3592**, so YOLO sees the
frame downscaled **8.4×**. Converting the median areas to a post-resize subject size:

| Group | median `area_frac` | approx. subject long side at `imgsz=640` |
|-------|--------------------|------------------------------------------|
| Detected | 0.0590 | **~155 px** |
| Missed | 0.0140 | **~76 px** |

A 76 px subject sits at the small-object limit for a 640 px YOLO input. The recall floor of
`area_frac` ≈ 0.04 corresponds to roughly **130 px on the long side after resize** — a
plausible detection threshold for this model and input size, and one that a long-lens wildlife
library will fall below constantly.

## What correlates, and what does not

The split follows **behaviour**, because behaviour determines subject size and separation here:

| Frames | Detector |
|--------|----------|
| Eagle in flight against sky or water (19 frames) | detected |
| Eagle perched on sandstone (36 frames) | missed |
| Wings-open on the ledge (`DSC_2196`, `DSC_2198`) | missed |
| One flight frame, distant (`DSC_2191`) | missed |

Perched frames are both smaller in frame and set against heavily textured sandstone of similar
tone to the bird's body. Size is the measurable driver; low subject/background separation is a
credible contributor that this single-folder sample cannot isolate.

`keywords` on these rows already say `wildlife` and `birds`, so downstream consumers had every
reason to expect a box.

## Box accuracy

Where the detector fired, the geometry was sound. `crops.load_oriented()` decoded `DSC_2160` to
exactly **5392 × 3592**, matching the stored `img_w`/`img_h`, so `bbox.rescale_box` was a no-op
and the stored coordinates landed pixel-exact. Crops rendered at `croppad25` were verified by eye
to be centred with correct padding.

One degenerate box: **`DSC_2169`** has `area_frac` **0.9314** at `conf` 0.66 — the box covers
93 % of the frame, so a "crop" from it is the full frame. Consumers that treat any non-sentinel
`bird_bbox` as a usable crop will silently process a full frame for this row. An `area_frac`
sanity ceiling would catch it.

## Why this matters beyond one folder

1. **`bird_species` classification is affected, not just crops.** Per
   [`phases/bird-species.md`](../architecture/pipeline/phases/bird-species.md), when
   `detect_best_box` returns the sentinel the phase **classifies the full frame** instead of a
   crop. For a 1.4 %-of-frame eagle, BioCLIP is being handed a picture of sandstone. Species
   results on small-subject frames should be treated as low-confidence.
2. **`{"detected": false}` is being read as "no bird".** The state is documented as evidence
   about the photo. On this material it is substantially evidence about **subject size versus
   `imgsz`**. Any recall or coverage metric built on it is optimistic.
3. **Ground-truth risk.** The bird-crop labelling study
   ([`BIRD_BBOX_CROP_STUDY_2026-08-01.md`](BIRD_BBOX_CROP_STUDY_2026-08-01.md)) selects bursts
   that *have* boxes. If the recall floor is size-dependent, the study population is biased
   toward larger subjects, and its conclusions may not transfer to typical long-lens frames.

## Suggested follow-ups (none performed)

- **Measure recall properly.** Sample frames with `{"detected": false}` across several folders
  and hand-check. One folder is not a rate.
- **Try `imgsz=1280` on the 39 misses** and compare. Cheapest test of the mechanism; if recall
  jumps, `bird_detection.imgsz` is the lever, and the config key already exists.
- **Consider tiled or two-pass inference** for small subjects rather than a global `imgsz` rise,
  which costs VRAM on every image.
- **Add an `area_frac` ceiling** (~0.9) that rejects a near-full-frame box as degenerate.
- **Re-check `conf=0.25`** against the missed set; if the model produced sub-threshold boxes for
  these frames, the fix is cheaper than a resolution change.

## Provenance and caveats

- Single folder, single species, single session — this is a **finding, not a measured rate**.
- The 39 "missed" areas are **hand-placed estimates by a vision model**, not ground truth. They
  were never written to `images.bird_bbox` and never entered `label_set.csv`. The 4.2× median
  separation is wide enough to survive estimation error; the exact 0.04 boundary is not.
- All database access was `SELECT` only. No detector re-run, no backfill, no code change.
- Produced during a run of `prompts/bbox-crop-score.md` in the sibling **image-scoring-skills**
  repo; per-image data lives in that repo's gitignored `work/disk/A41*/score/`.

## Related

- [`phases/bird-species.md`](../architecture/pipeline/phases/bird-species.md) — phase contract, sentinel semantics
- [`BIRD_BBOX_CROP_STUDY_2026-08-01.md`](BIRD_BBOX_CROP_STUDY_2026-08-01.md) — crop study this may bias
- [`localization-rollout.md`](../architecture/pipeline/localization-rollout.md) — detector rollout
- [`CANONICAL_SOURCES.md`](../CANONICAL_SOURCES.md) — contract authority
- `modules/bird_detection.py`, `scripts/research/bird_crop/{bbox,crops}.py`