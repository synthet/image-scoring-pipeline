---
type: Report
title: Subject detector comparison — bird YOLO vs an open COCO detector on the #377 cohort
description: On the owner-labelled #377 cohort, an open COCO detector (RTMDet-tiny) at 640 input matches the bird YOLO's 1280 recall on 640-misses with ~1/16 of the false positives, rejects most of the YOLO's false boxes, and agrees on box geometry (median IoU 0.82).
resource: docs/reports/subject-detector-comparison-2026-09-24.md
tags: [research, localization, detector, bird-detection, benchmark, clean-room]
timestamp: 2026-09-24T00:00:00Z
okf_version: 0.1
---

# Subject detector comparison (2026-09-24)

> **Status:** research memo, read-only. It extends the
> [#377 detector benchmark](detector-benchmark-2026-09.md) with one more arm, using the same cohort,
> labels and definitions. Production is unchanged. The work is relevant to
> [localization rollout](../architecture/pipeline/localization-rollout.md) Stages 3–4 and to the
> detector role in [subject-evidence model roles](../planning/models/subject-evidence-model-roles.md).

## Provenance (clean-room)

The new arm reproduces the subject-detection **policy** of a reference wildlife-culling design, as
observed from its behaviour:
- an open, general-purpose COCO detector, **RTMDet-tiny** (OpenMMLab, Apache-2.0)
- run on an ~800 px embedded-preview rendition, letterboxed to 640
- subject classes = COCO animals (plus person)
- confidence ≥ 0.4, retrying at 0.25 when nothing passes
- NMS at IoU 0.7

The ONNX weights used were taken from a locally installed copy of that design. **Before any adoption,
re-run with the upstream OpenMMLab COCO checkpoint** and confirm the numbers hold. No code from the
reference product is involved.

## Method

- **Cohort and labels:** unchanged from #377.
  - 339 frames; 280 owner-labelled blind (179 bird, 99 no_bird, 2 unsure) plus 59 eagle positives.
  - Unsure labels are excluded.
- **Metric:** frame presence, as in #377. A hit is ≥ 1 retained box.
  - Recall = hits / labelled bird.
  - False-positive rate = frames with a hit / labelled no_bird.
- **YOLO arms:** taken from #377 `results.csv` (`a640`, `a1280`, `tile`), not re-run.
- **Reference arms:** computed from the policy boxes in three variants:

  | Arm | Classes kept |
  |---|---|
  | `ref_subject` | person + animals |
  | `ref_animal` | animals only |
  | `ref_bird` | COCO bird only |

- **Selection bias:** the `det_*` strata were sampled from YOLO-640 detections, and the `miss_*`
  strata from YOLO-640 misses. YOLO-640 is therefore 100% or 0% on them by construction.
- **Fair comparison:** the three strata **not selected on the new detector's output** (`miss_birdkw`,
  `miss_nokw`, `eagle`, "independent" below). There, every arm except YOLO-640 is unselected. As in
  #377, nothing is pooled into a library-wide rate.

## Recall on labelled birds

| Stratum | YOLO 640 | YOLO 1280 | YOLO tile | ref_subject | ref_animal | ref_bird |
|---|---|---|---|---|---|---|
| `det_small` | 48/48 | 48/48 | 48/48 | 47/48 | 47/48 | 47/48 |
| `det_medium` | 36/36 | 36/36 | 36/36 | 36/36 | 36/36 | 35/36 |
| `det_large` | 17/17 | 17/17 | 17/17 | 17/17 | 17/17 | 17/17 |
| `miss_birdkw` | 0/73 | 56/73 (77%) | 50/73 (68%) | 66/73 (90%) | 65/73 (89%) | 65/73 (89%) |
| `miss_nokw` | 0/5 | 3/5 | 4/5 | 5/5 | 5/5 | 5/5 |
| `eagle` | 20/59 (34%) | 53/59 (90%) | 46/59 (78%) | 58/59 (98%) | 57/59 (97%) | 39/59 (66%) |
| **independent** | 20/137 (15%) | **112/137 (82%)** | 100/137 (73%) | 129/137 (94%) | **127/137 (93%)** | 109/137 (80%) |

## False-positive rate on labelled no_bird

| Stratum | YOLO 640 | YOLO 1280 | YOLO tile | ref_subject | ref_animal | ref_bird |
|---|---|---|---|---|---|---|
| `det_small` | 2/2 | 2/2 | 2/2 | 1/2 | 0/2 | 0/2 |
| `det_medium` | 14/14 | 13/14 | 14/14 | 10/14 | 6/14 | 4/14 |
| `det_large` | 12/12 | 11/12 | 12/12 | 11/12 | 9/12 | 3/12 |
| `miss_birdkw` | 0/17 | 10/17 | 6/17 | 6/17 | 5/17 | 5/17 |
| `miss_nokw` | 0/54 | 35/54 (65%) | 30/54 (56%) | 22/54 (41%) | 7/54 (13%) | 4/54 (7%) |
| **independent** | 0/71 | **45/71 (63%)** | 36/71 (51%) | 28/71 (39%) | **12/71 (17%)** | 9/71 (13%) |

The YOLO-640 false positives in `det_*` are 28 frames that the owner labelled bird-free. `ref_bird`
keeps only **7/28** of them, and `ref_animal` 15/28.

## Operating points (independent strata, threshold sweep)

| Arm | Threshold | Recall | FP rate |
|---|---|---|---|
| YOLO 1280 | 0.25 | 82% | 63% |
| YOLO tile-on-miss | 0.25 | 73% | 51% |
| ref_animal | 0.5 | 65% | 3% |
| **ref_animal** | **0.4** | **82%** | **4%** |
| ref_animal | 0.3 | 92% | 14% |
| ref_bird | 0.25 | 80% | 13% |
| ref_bird | 0.15 | 97% | 18% |

At equal recall to YOLO-1280 (82%), the open detector at 640 input has a **4% vs 63%** false-positive
rate on this cohort.

## Class behaviour

- **Eagle slice:** the open detector labels 26/59 frames `bear`. The subject is a dark raptor against
  textured bark. As a result, `ref_bird` (66%) is far below `ref_animal` (97%). **Treat the COCO class
  as a hint, not a gate.** Accept any animal class as "subject present", then let BioCLIP decide
  species (Stage 5).
- **Person:** on bird-free `miss_nokw` frames, 17/54 are detected as `person`. That is why
  `ref_subject` has the worst FP rate of the reference arms. Exclude person for wildlife localization.
- **Hard misses:** 30 labelled-bird frames have no bird-class box at the default policy. Their best
  bird confidences are 12 in 0.20–0.25, 15 in 0.10–0.20 and 3 in 0.05–0.10. Unlike the YOLO (60/117
  with nothing ≥ 0.05), the open detector almost always has a weak candidate.

## Box agreement

There are 119 frames where both YOLO-640 and `ref_animal` detect and the label is bird. No
orientation mismatches occurred.

| Slice | n | Median IoU |
|---|---|---|
| all | 119 | **0.82** |
| `det_small` | 47 | 0.77 |
| `det_medium` | 36 | 0.85 |
| `det_large` | 17 | 0.85 |
| `eagle` | 19 | 0.91 |

- 82% of these frames have IoU ≥ 0.5, and 5% have IoU < 0.1 (a different object picked).
- The open detector's bird boxes on labelled birds range from 0.0011 to 0.84 area fraction (median
  0.022). None is ≥ 0.90, so the near-full-frame artefact seen twice at YOLO-640 did not occur.

## Cost

Both timings are on the CPU of the research workstation:

| Step | p50 | p95 |
|---|---|---|
| 800 px embedded-preview rendition | 66 ms | 92 ms |
| RTMDet-tiny inference | 95 ms | 117 ms |

These are not directly comparable to #377's GPU numbers (YOLO 146 ms p50 plus a 507 ms full decode),
but they show that an embedded-preview route plus a tiny CPU detector is cheap enough for "localize
every new image" (epic, Stage 4).

## Why the gap is plausible

The #377 report records the YOLO's training data:
- 1,752 validation boxes with minimum area 0.0597 (median 0.31)
- roughly 300–500 px source images
- **no negative images**

It has never seen a small bird or a bird-free frame. The open COCO detector was trained on 118k
varied images, with small objects and abundant negatives. Both run at about 640 px here, so the gap
comes from the **model and its training data, not input resolution**.

## Recommendations

1. **Add the open detector as a Stage 3 benchmark arm and a Stage 4 candidate provider.** This is
   additive: a new `detector_key`, versioned like the YOLO. Shadow only, and no production default
   changes until the epic's gates pass. The epic already allows multiple providers.
2. **Provider policy:**
   - animal classes (no person), confidence ≥ 0.4, retry at 0.25
   - persist all boxes with their COCO class as `provider_class_id`
   - `object_class = animal`, so class does not gate presence
3. **Keep the YOLO where it is strong:** its boxes agree closely on the birds it finds (median IoU
   0.82). A cross-check is cheap: if both detect, prefer the YOLO box for continuity with
   `bird_bbox`; if only the open detector does, record the region at lower authority. The
   `yolo640 ∧ ref_animal` agreement arm already removes 13 of the 28 YOLO false positives in `det_*`
   while keeping 100/101 true detections.
4. **Improve the YOLO's training set** (image-scoring-model):
   - add hard negatives and sub-0.05-area birds
   - optionally pseudo-label from the open detector on our library, with human spot checks
5. **Before adopting:**
   - re-run with upstream OpenMMLab weights
   - retain full box records (the #377 follow-up)
   - label boxes, not just presence, on a slice, so localization quality (IoU vs human) can be
     measured rather than inferred from agreement

## Reproduce

The research instrument lives outside this repo. It reads `cohort.csv`, `labels.csv` and
`results.csv` from [detector-benchmark-2026-09/](detector-benchmark-2026-09/) and the DB (read-only),
and caches raw detections (all classes ≥ 0.05, normalized preview coordinates, timings) per image. A
repo-native arm should be added to `scripts/research/detector_benchmark/run_benchmark.py` once the
upstream checkpoint is chosen.
