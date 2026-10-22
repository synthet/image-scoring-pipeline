---
type: Report
title: Timing baseline on the 8 GB card
description: Pinned decode, localization and scoring timing baseline, routing caveats and rollout cost gates.
resource: reports/timing-baseline-2026-10-18.md
tags: [localization, benchmark, timing, report]
timestamp: 2026-10-18T21:55:37Z
okf_version: 0.2
---

# Timing baseline on the 8 GB card

Issue [#416](https://github.com/synthet/image-scoring-pipeline/issues/416), supporting
the [localization rollout](../architecture/pipeline/localization-rollout.md).
Three production-path repeats are complete. This report records measurements and
their limits; it does not authorize a detector/rendition change or crop promotion.

## Cohort and method

- Pinned seed **416**, **170 images**: 100 RAW with a current v1 detection,
  50 RAW with a current v1 miss, and 20 JPEGs. The library contained 78,983 NEFs
  and 812 JPEGs when sampled; the JPEG stratum was drawn separately because very
  few JPEGs had a current v1 run. This is a cost sample, not a labelled quality gate.
- [Sanitized cohort](timing-baseline-2026-10-18/cohort.json) retains image IDs and
  strata, with private file paths removed. Original private cohort SHA-256:
  `b10fc1b253eaf4f8c3d30e0a68da6746989cb366ffa20e1889769bdcfc048e7f`.
- Harness `scripts/research/timing_baseline/measure_timing.py` (pending its #416 PR) uses
  `perf_counter`, with CUDA synchronization before and after Torch calls.
  The first three calls per stage per repeat are excluded; each single model-load
  observation is retained. Percentiles use linear interpolation. The tables average
  each repeat's p50/p95; CV is sample standard deviation of repeat medians / mean.
- Every full stage has **170 calls in each repeat** (167 after warm-up); crop IQA
  has **114** (111 after warm-up). Timed sample keys are unique. Alternative decode
  routes were attempted on the first 30 RAWs per repeat.
- Pass A holds scene CLIP, the configured detector route and BioCLIP together.
  Pass B preprocesses scoring inputs, then calls the path-based IQA/keyword/caption
  models and finally TensorFlow MUSIQ. Model load times include available cache
  and routing initialization costs; these are not cold-download times.
- RTX 4060 Laptop GPU, 8,188 MiB; Torch **2.10.0**, ultralytics **8.4.120**,
  onnxruntime **1.22.1** in gpu-shell. Available ONNX providers were Azure and CPU;
  **RTMDet GPU was unavailable**. **ImageMagick was absent**. Neither route has a
  fabricated latency or VRAM estimate.

## Production-path latency

| Stage | Calls after warm-up / repeat | Mean p50 ms | Mean p95 ms | p50 CV |
|---|---|---:|---:|---:|
| `arniqa:crop` | [111, 111, 111] | 52.859 | 189.381 | 0.2578 |
| `arniqa:full` | [167, 167, 167] | 27.142 | 56.858 | 0.1748 |
| `bioclip_encode` | [167, 167, 167] | 141.858 | 280.662 | 0.0758 |
| `blip_caption:full` | [167, 167, 167] | 588.718 | 1124.489 | 0.1645 |
| `clip_b32_keywords:full` | [167, 167, 167] | 136.482 | 214.642 | 0.1183 |
| `decode:production` | [167, 167, 167] | 801.393 | 2758.687 | 0.336 |
| `decode_alt:raw_jpgfromraw` | [27, 27, 27] | 458.867 | 1307.104 | 0.4294 |
| `decode_alt:raw_preview` | [27, 27, 27] | 355.933 | 1516.978 | 0.5161 |
| `decode_alt:rawpy` | [7, 7, 7] | 21186.179 | 36219.021 | 1.0139 |
| `liqe:crop` | [111, 111, 111] | 65.761 | 354.647 | 0.5716 |
| `liqe:full` | [167, 167, 167] | 33.569 | 88.009 | 0.0635 |
| `musiq_ava:full` | [167, 167, 167] | 40.0 | 51.388 | 0.1274 |
| `musiq_spaq:full` | [167, 167, 167] | 39.056 | 46.244 | 0.0219 |
| `rtmdet_cpu` | [167, 167, 167] | 184.096 | 432.979 | 0.2481 |
| `scene_clip` | [167, 167, 167] | 227.118 | 654.003 | 0.4453 |
| `scoring_preprocess` | [167, 167, 167] | 1636.306 | 17266.672 | 0.1954 |
| `topiq:crop` | [111, 111, 111] | 82.986 | 212.785 | 0.3029 |
| `topiq:full` | [167, 167, 167] | 39.149 | 81.431 | 0.2718 |
| `yolo640` | [167, 167, 167] | 2292.39 | 6916.996 | 0.256 |

Full-frame IQA means the scoring backend's converted/preprocessed full-frame input;
crop IQA uses saved subject crops. BioCLIP timing is the image tower only: crop
selection, preprocessing, text scoring, persistence and XMP are excluded.
RTMDet includes its CPU detector path, not an end-to-end cascade/refinement run.

The route census was **150 `raw_jpgfromraw` + 20 direct decodes per repeat**.
Rawpy succeeded on only 10/30 diagnostic RAWs per repeat; 20 errors are counted
separately, including unsupported Nikon HE NEFs. After warm-up, rawpy has seven
successful timings per repeat. Its medians were 8,683 / 8,887 / 45,989 ms, so its
large variance must not be used as production decode cost. Scoring preprocessing
also has a long tail. No pipeline jobs overlapped the measurement interval:
read-only SQL checked the conservative 14:41:59–21:47:37 UTC window on October 18.

## Local control and invalid keypoint samples

Effective configuration routes localization through `RemoteBirdDetector`. Its
`_predict_raw_boxes` PNG-encodes the full decoded frame before the remote/fallback
client. The main `yolo640` measurement therefore includes transport serialization
and routing/failover overhead; it is **not a local GPU forward-pass measurement**.
The [#377 benchmark](detector-benchmark-2026-09.md) used direct local inference,
different weights and a different cohort. The difference cannot be attributed to
CPU resizing alone, or treated as a detector regression without a matched control.

The production keypoint context was **disabled**. The original harness tested only
`load_error`, then called `infer_region_keypoints` with no loaded model; that API
returns an error outcome rather than raising. Its apparent 0.864 ms median measures
failed calls. **Those values are excluded from valid inference results here**;
the [raw summary](timing-baseline-2026-10-18/summary.json) explicitly marks them invalid.

A supplementary control used the first ten RAW-bird IDs from the same cohort,
three repeats, the same three-call warm-up policy, explicit **local CUDA** YOLO,
and an **enabled** keypoint provider. HF/Transformers were offline, and no remote
requests or database/config writes were used. This smaller control distinguishes
serialization from local inference; its seven retained samples per repeat do not
replace a 170-image keypoint or detector-quality study.

| Stage | Calls after warm-up / repeat | Mean p50 ms | Mean p95 ms | p50 CV |
|---|---|---:|---:|---:|
| `transport:encode_png` | [7, 7, 7] | 1948.646 | 3083.566 | 0.2351 |
| `local_yolo640` | [7, 7, 7] | 328.962 | 653.23 | 0.2542 |
| `enabled_keypoints` | [7, 7, 7] | 46.511 | 68.046 | 0.4517 |

Control provider/error counts: `{}`. Details, IDs, times and
weight hashes: [local-control.json](timing-baseline-2026-10-18/local-control.json).

## Model load and memory

There is one load observation per model per repeat, so no within-repeat load p95
is meaningful. Values below retain all three observations.

| Model | Load ms, repeats 1 / 2 / 3 | Mean ms | CV |
|---|---|---:|---:|
| `arniqa` | [516.1, 644.139, 1247.574] | 802.604 | 0.4867 |
| `bioclip` | [5031.512, 13844.001, 11133.415] | 10002.976 | 0.4512 |
| `blip_caption` | [3267.022, 4318.208, 3314.435] | 3633.222 | 0.1634 |
| `clip_b32_keywords` | [4159.02, 2931.824, 2415.937] | 3168.927 | 0.2826 |
| `keypoints (disabled context)` | [10.32, 3.608, 10.015] | 7.981 | 0.4749 |
| `liqe` | [5155.263, 8829.097, 8206.189] | 7396.849 | 0.2658 |
| `musiq_ava` | [14277.623, 9101.242, 23554.793] | 15644.553 | 0.4681 |
| `musiq_spaq` | [7334.817, 5415.305, 10560.296] | 7770.139 | 0.3346 |
| `rtmdet_cpu` | [633.56, 411.074, 514.243] | 519.626 | 0.2143 |
| `scene_clip` | [13427.178, 13628.243, 14192.818] | 13749.413 | 0.0289 |
| `topiq` | [1777.767, 863.749, 1782.013] | 1474.51 | 0.3587 |
| `yolo640` | [25216.651, 26311.979, 24185.694] | 25238.108 | 0.0421 |

Repeat-3 memory is available; the interrupted original command did not persist
repeat-1/2 memory metadata. These are **process allocator peaks observed at each
stage**, including co-resident allocations, not exclusive model memory. TensorFlow
SPAQ/AVA share its allocator's peak and cannot be summed as isolated requirements.

| Repeat-3 stage | Observed peak allocated MiB |
|---|---:|
| `pass_a_loaded_together` | 3073.7 |
| `pass_a_after_cohort` | 3101.8 |
| `liqe` | 1523.9 |
| `topiq` | 1298.9 |
| `arniqa` | 1091.8 |
| `clip_b32_keywords` | 707.3 |
| `blip_caption` | 1204.7 |
| `musiq_spaq` | 1009.7 |
| `musiq_ava` | 1009.7 |

Whole-card snapshots were 3,871 MiB at repeat-3 start and 4,871 MiB at its end;
an intermediate process inspection observed 5,879 MiB, including WebUI allocations.
These snapshots are not a sampled whole-run peak. Preserve one heavy GPU job at a
time. [Memory metadata](timing-baseline-2026-10-18/repeat3-memory.json) records
repeat 3 from 2026-10-18T20:53:18.302892+00:00 to 2026-10-18T21:47:36.330946+00:00 with zero overlapping jobs.

## Recovery and rollout decisions

Repeats 1 and 2 completed at 15:23:58 and 15:48:31 UTC. The original process was
killed during repeat 3; its partial rows were saved separately and **excluded**.
Only the replacement repeat 3 contributes here. The retained private timing file
SHA-256 is `4fcede7f8e09926b592738590c79588f40cab284496b2acd82c7ae458685f35f`.

- **Stage 7 cost gate:** production decode plus routed YOLO has a sum of medians
  of approximately **3.094 s/image**. This is a planning proxy, not a measured
  mean throughput or p95 budget; scene routing, cascade/refinement, I/O tails and
  orchestration must be included in a timed pilot. Apply the eligible/candidate
  ratio from current SQL, rather than projecting this cost onto every image.
- **#641 repair:** BioCLIP encode is about 142 ms, but it excludes full-frame
  preprocessing and uses crops on detected frames. Do not turn it into a firm
  33,764-image rebuild ETA. A bounded 200-image full-frame pilot sets that ETA.
  Rebuild only the frozen repair IDs; an unrestricted missing-row backfill would
  also fill 1,631 pre-existing gaps and the 4,029 moved crop-only images.
- **2048 px / detector choice:** keep current defaults. A matched rendition and
  per-stratum quality gate is still required; this latency report does not supply it.
- **Stage 6:** crop IQA timings are available, but crop/fusion adoption remains
  under research epic #645 and its owner-labelled burst gates.
- **Coverage limits:** ImageMagick and GPU RTMDet remain unmeasured. Keypoint
  inference is a ten-image control, and per-model exclusive VRAM remains unmeasured.
  Keep #416 open for review of those limitations rather than silently declaring
  every requested measurement delivered.

## Verification

All expected full/crop call counts, distinct cohort IDs, local control counts and
unique timed keys were checked before generating the report. Regression coverage
retains model loads and excludes disabled/failed keypoint calls from latency
samples, while retaining valid detected/no-keypoint outcomes (**12 passed**);
ruff passed. The source fixes apply to future runs; the invalid old keypoint rows
remain preserved and explicitly annotated in the published summary.
No scores, labels, selections, rollout flags or production embeddings changed.
