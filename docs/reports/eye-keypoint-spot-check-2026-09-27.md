---
type: Report
title: Eye keypoint backfill and spot check (2026-09-27)
description: Library-wide shadow backfill of bird head keypoints (eye-pose-v0, top-down on the primary region) and a 110-item blind spot check by three agentic CLI vision judges adjudicated with Jev - accuracy, coverage, false negatives and false positives.
resource: docs/reports/eye-keypoint-spot-check-2026-09-27.md
tags: [report, localization, keypoints, eye, shadow, judge-panel]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.1
---

# Eye keypoint backfill and spot check (2026-09-27)

> **Status:** shadow data, triage estimate. No human labels were used; every number is a starting point to re-fit
> against owner-checked points. Supports [#426](https://github.com/synthet/image-scoring-pipeline/issues/426).

## Backfill

Provider `bird_head_pose` ([modules/keypoints.py](../../modules/keypoints.py)): the image-scoring-model
`eye-pose-v0` YOLO pose model (six points: beak, both eyes, head top, both shoulders) run **top-down** on a 25%-padded
crop of the rank-0 `bird` region. Stored in `image_keypoint_runs` / `image_region_keypoints` (migration 0036),
display-normalized like the regions. Script: `scripts/backfill_region_keypoints.py --localize-missing`.

| | images |
|---|---|
| Candidates (bird-tagged, legacy box found a bird) | 21,380 |
| Pose found the bird (`detected`) | 20,165 |
| ... with an eye above the provider gate (0.25) | 19,550 |
| Pose found no bird in the crop (`no_keypoints`) | 1,215 |
| File missing / undecodable | 7 / 1 |

Throughput on the 8 GB laptop GPU: 0.6-2.3 s per image, dominated by decoding the full-size embedded JPEG of 45 MP
NEFs (about 1.5 s), not by inference (detector about 0.4 s, pose about 0.1 s). This is direct evidence for
decode-once renditions (#406).

## Spot check

Blind panel: 110 items sampled with a fixed seed, three agentic CLI vision judges (a fourth was rate-limited), each
answering per item: marker A/B **ON** the eye / **NEAR** (within about one eye-width) / **OFF**; how many eyes of the
boxed bird are visible (0/1/2); does the box hold a bird. Judges saw a padded crop with the box and markers plus a
full-resolution zoom, with no scores or strata. Jev (TypeSafe System One) adjudicated 295 questions from the votes and
reasons. Each judge agreed with the adjudicated marker verdict on 95-97% of markers (kappa 0.90-0.95).

### Accuracy (weighted to the library)

| Max eye confidence | Share of library | ON | ON or NEAR | OFF |
|---|---|---|---|---|
| >= 0.8 | 92% | 32% | 74% | 26% |
| < 0.8 | 8% | 0% | 10% | 90% |
| All | | ~30% | ~69% | ~31% |

- **Confident points are close, rarely exact.** The typical miss is about one eye-width behind or below the eye at
  full resolution: fine for a head crop, not for measuring sharpness *on* the eye.
- **Below 0.8 the points are nearly always wrong:** eyes placed on the back of the head of a bird facing away, on a
  tail when the box cut the head off, or in boxes with no bird. Judges saw no eye at all in 19 of 30 such frames.
- **Consequence:** consumers treat an eye as found only at confidence >= 0.8
  (`modules.keypoints.EYE_CONSUMER_MIN_CONF`). The stored `visible` flag keeps the provider's permissive gate for
  calibration work.

### Coverage and misses

| Group | Library | Sampled | Judges see a visible eye |
|---|---|---|---|
| Pose ran, no eye above the gate | 615 | 25 | 16% (about 100 images) |
| Pose found no bird in the crop | 1,212 | 25 | 36% (about 440 images) |

- Missed second eye (one marker, two eyes visible): 0 of 60.
- Box holds no bird: about 2% of confident-eye frames, 20-25% in the low-confidence and no-keypoint groups (detector
  false positives, or boxes far too loose for the head to be found).

## Next

1. An owner-checked eye set (start from the panel's review list of 72 items) to replace this estimate and re-fit the
   0.8 threshold.
2. Retraining the eye model only on points >= 0.8, treated as approximate; see the model repo's
   self-supervised landmark plan for the head-crop route.
3. Better boxes help most: the detector cascade (#408) and the teacher-labelled `bird_detect_v0` retrain.

## Related

- [localization rollout](../architecture/pipeline/localization-rollout.md) (stage 2 addendum, stage 4 providers)
- [subject-evidence model roles](../planning/models/subject-evidence-model-roles.md)
- image-scoring-model: [eye-location-density.md](https://github.com/synthet/image-scoring-model/blob/main/docs/planning/eye-location-density.md), [ssl-landmark-pretraining.md](https://github.com/synthet/image-scoring-model/blob/main/docs/planning/ssl-landmark-pretraining.md)
