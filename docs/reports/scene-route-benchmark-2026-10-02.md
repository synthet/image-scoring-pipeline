---
type: Report
title: Scene route benchmark
description: Owner-labelled benchmark of zero-shot and probe scene classifiers on the localization rendition, the frozen bird-route threshold (SigLIP2, p >= 0.065), and its effect on the v1 false detections.
resource: reports/scene-route-benchmark-2026-10-02.md
tags: [report, scene-route, localization, clip, siglip, benchmark]
timestamp: 2026-10-02T00:00:00Z
okf_version: 0.2
---

# Scene route benchmark (2026-10-02)

Spec 05 ([scene route](../specs/pipeline-streamlining/05-scene-route.md), #412) classifies each
image before localization, so that the bird detector runs only where a bird is plausible and
every other scene keeps the full frame. This report covers the benchmark gate (AC-1 to AC-4).
The harness is [`scene_benchmark.py`](../../scripts/research/scene_route/scene_benchmark.py).
Artifacts stay in gitignored `.agent/scratch/scene_route/`.

## Method

- **Input.** Each image is classified on the orientation-correct localization rendition
  (`decode_for_localization`), not on stored CLIP vectors. Stored vectors are sideways for
  portrait RAWs (#418, SR-4).
- **Classes (`scene_v2`).** The classes come from the library's keyword frequencies. Classed
  exclusively by subject priority, the library is bird 51%, other animal 8%, urban/architecture
  7%, landscape 6%, insect 6%, people 4%, vehicles 3% and plants/flowers 3%. Reptiles and
  amphibians have no keyword, so they sit in `other_animal`.
- **Arms.** The zero-shot arms are OpenAI CLIP B/32, OpenCLIP B/32 (LAION-2B), OpenCLIP L/14
  (LAION-2B) and SigLIP2-base. A supervised-transfer arm sums ImageNet-22k ConvNeXt class
  probabilities into animal groups. Each embedding also gets a folder-grouped, out-of-fold
  logistic-regression probe. Every pool image's resolved class is saved to `image_scene_labels`.
- **Sample.** A pool of 3,586 images was drawn library-wide, at most 8 per folder, excluding
  earlier labelled sets. From it, 519 images were sampled, about 60 per B/32-predicted class and
  at most one per folder per class. Metrics are weighted by population per stratum.
- **Labels.** The owner labelled every image blind: one main scene, plus whether *any* bird is
  visible. Claude also labelled all 519 as an AI second opinion. It agreed with the owner on 457
  scenes and 499 bird answers. Codex and Antigravity stopped at 180 and 120 images on quota
  limits, so the owner labels are the only ones used below.

## Scene classification (owner labels, weighted)

| Arm | Macro F1 | Accuracy | Bird precision | Bird recall |
|---|---:|---:|---:|---:|
| **SigLIP2-base (zero-shot)** | **0.750** | 0.820 | 0.848 | **0.968** |
| Probe on SigLIP2 | 0.757 | 0.873 | 0.906 | 0.954 |
| Probe on OpenCLIP L/14 | 0.738 | 0.856 | 0.895 | 0.933 |
| OpenCLIP L/14 | 0.721 | 0.794 | 0.904 | 0.928 |
| OpenAI CLIP B/32 | 0.696 | 0.765 | 0.883 | 0.881 |
| OpenCLIP B/32 (LAION) | 0.651 | 0.738 | 0.841 | 0.886 |

SigLIP2 is the strongest training-free arm. Its probe gains accuracy but needs labelled training
data, and gives the bird route no advantage (below). SigLIP2's weak classes are vehicles
(precision 0.36, with only 15 owner-labelled vehicle images), other animal (recall 0.58) and
landscape (recall 0.67).

## Bird route (AC-3, AC-4)

The 519 images include 77 owner-labelled images with a bird visible anywhere, against 70 where a
bird is the main subject. AC-4 caps the share of bird-visible images that would skip the
detector at 2%. For each arm, the largest threshold meeting that cap:

| Arm | Score | Threshold | Bird-visible skipped (weighted) | Skipped / labelled | Non-bird images still detected |
|---|---|---:|---:|---:|---:|
| **SigLIP2-base** | p(bird) | **0.065** | 1.6% | 5 / 77 | **24.6%** |
| OpenAI CLIP B/32 | p(bird) | 0.04 | 1.8% | 4 / 77 | 43.2% |
| OpenCLIP L/14 | cosine | 0.12 | 1.7% | 4 / 77 | 45.7% |
| Probe on SigLIP2 | p(bird) | 0.10 | 2.0% | 5 / 77 | 37.4% |
| ImageNet ConvNeXt | p(any animal) | 0.015 | 0% | 0 / 77 | 96.5% |

Selection rule, declared in the harness before labelling: the arm that sends the fewest
non-bird images to the detector within AC-4. **Frozen:** SigLIP2-base, `wildlife_bird` probability
≥ 0.065 (`scene_v2/siglip2_base/f497b4a991ec716d`).

- **What the skip costs.** All five skipped bird images are incidental birds in landscape or city
  scenes. No image with a bird as its main subject is skipped.
- **Weighted rate versus raw count.** The 1.6% is population-weighted. The raw 5 of 77 has a
  Wilson 95% upper bound of 14%. AC-4 is therefore met as a point estimate but not
  demonstrated with confidence. A larger bird-containing sample would tighten it.
- **Saving.** At this threshold the bird detector skips about three in four non-bird images.

**Side check on the v1 shadow detections.** This check reuses the owner presence labels from the
v1 reviews; the frames are selection-biased. At the frozen threshold:
- the route skips **114 of 182** owner-labelled no-bird false detections (63%);
- it skips **1 of 240** bird frames.

That is the no-bird signal the [v1 promotion gate](bird-v1-promotion-gate-2026-10-01.md) lacked.
It can be used in a new frozen promotion rule, validated on a fresh sample.

## Decision and next steps

- **Ship SigLIP2-base as the scene classifier.** Use run threshold `{"wildlife_bird": 0.065}`
  for the bird route, which is behind `scene_route.enabled` (default off, Milestone C, c34e2e0).
  Enable it first on new imports, and watch the `scene_route` skip counts in localization job
  summaries.
- **Keep the residual risk visible.** Skipped incidental birds keep the full frame. Bird species
  still runs on keyword-positive images, using the full frame, so it does not depend on this
  route.
- **Follow-ups:**
  - widen the bird-containing sample to bound AC-4 tightly;
  - re-gate the v1 shadow boxes with the scene route as a false-positive filter;
  - route `other_animal` to a mammal detector once one is benchmarked;
  - improve the vehicles and other-animal prompts in a `scene_v3`.

| Frozen input | SHA-256 |
|---|---|
| `pool.csv` | `def02483756adb5c7e1ffc257960be0f00fef9093b622e00486c6452209aa3dc` |
| `sample/cohort.csv` | `c8b2a89fc0cb03db5d93d8e58fbed9550b2bcec4b51825b0e74d983606b6e94e` |
| `sample/sampling.json` | `2c1cc9c62d279f4a35912e88ea1ffab287cc16fde21ce514e97814a1a81c950c` |
| `sample/labels_owner.csv` | `cd177be0c6534379925517c1e98e9a5317b1297f7fca5c99dab9c75285cd3a4c` |
| `analysis_labels_owner.json` | `e04e11693a63907dcb6184916ba41851a1c972c3bb5b7543b0521f8fa3091383` |
