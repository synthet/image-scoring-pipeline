---
type: Report
title: Labeled scoring-input benchmark results
description: Five-model owner-labeled preprocessing comparison, reproducible evidence and hold decision.
resource: planning/scoring-inputs/BENCHMARK-RESULTS.md
tags: [scoring, benchmark, orientation]
timestamp: 2026-10-06T23:53:11Z
okf_version: 0.2
---
# Labeled scoring-input benchmark results

Decision: **HOLD for every model and shared-cache scoring adoption**. Keep existing production resolution, padding, decoder and JPEG defaults. This completed comparison supplies evidence for [#570](https://github.com/synthet/image-scoring-pipeline/issues/570); representative coverage and resource gates remain open. Orientation/routing fixes are independent and locally verified in [VERIFICATION.md](VERIFICATION.md).

## Frozen sample and exclusions

The owner supplied `D:/Dropbox/Photos/Scoring/model-selection-2026-10-01`. Study `fe26c0e771036242`, sampling seed 20261001, uses a frozen library snapshot and human blind reviews. The study's initial REPORT.md predates the completed labels; the latest completed human review per unit was read from one export, without pooling duplicate exports.

Of 130 completed human-reviewed units, 94 single-image units were excluded from within-group pick agreement. Four multi-image units were all-reject and had no starred best; they were excluded from forced-pick evaluation and must be retained for a future reject-all policy evaluation. The remaining **32 units (14 bursts, 18 stacks), 24 independent blocks and 121 unique accessible NEFs** form this comparison. There are no duplicate image sets. Split membership was preserved: 22 train, eight validation and **two test units**. No model training or tuning was performed.

Coverage is **116 landscape and five portrait images**, spanning 30 landscape and two portrait units. There are no square/extreme-aspect or raster JPEG source strata. All shared-cache decode routes in this sample were `raw_jpgfromraw`. This owner-selected sample is not a weighted estimate of library-wide quality. The tiny portrait/test subsets cannot establish generalization or checkpoint adoption.

Original source hashes were unchanged. Every shared-cache hit/miss pair had identical decoded pixels. Original paths, full manifests, individual labels and image previews remain private in ignored `.agent/scratch/scoring-input-issues/`; the hashes below identify the reproducible local inputs without publishing the owner's photos.

## Policies and checkpoints

- `square512`: corrected upright pipeline source, bicubic inside-fit without upscale, black square padding, JPEG quality 85; baseline outer policy.
- `inside512`: same corrected source, bicubic 512 px long-edge inside-fit without padding, JPEG quality 85. Both axes retain proportions. Model-specific downstream transforms still apply.
- `cache_square512`: local shared rendition capped at 2048 px and JPEG quality 90, then the normal square512 preprocessor at quality 85. This combines decode/cap/round-trip effects; it does not isolate JPEG compression.

Executor **5.2.0**, orientation policy **upright-v1**, benchmark/summarizer hashes below; TensorFlow **2.20.0**, pyiqa **0.1.16**. Cached licensed weights were used, with no download or configuration/database/XMP writes. Checkpoints were TF Hub `google/musiq/spaq/1` and `google/musiq/ava/1`, LIQE KonIQ with 224 px patches and wrapper cap 518, TOPIQ-NR `cfanet_nr_koniq_res50` with wrapper cap 1024, and ARNIQA KonIQ regressor with wrapper cap 1024. [Installed-contract review and pre-recorded gates](RESEARCH-REVIEW.md).

All five models ran across all 121 sources and three variants: **1,815 measured inferences, zero failed variants**, plus warmups. The full labeled run used one measured repetition per input on CPU, with four PyTorch threads. Earlier three-source SPAQ/AVA pilot results remain separate in VERIFICATION.md.

## Human pick agreement

Best match means a model's highest-score pick belongs to the human's starred best set. For tied highest scores, the metric credits the fraction of tied candidates in that set. Units receive equal weight; no production fusion weights changed. Grade 0 is human reject, grade 1 keep and grade 2 pick. Multiple starred bests are allowed. Agreement with legacy ranking is reported separately and is not quality evidence.

| Model | Square best match | Inside best match | Cache best match | Inside changed winners | Cache changed winners |
| --- | --- | --- | --- | --- | --- |
| SPAQ | 43.75% | 40.62% | 43.75% | 10 | 0 |
| AVA | 37.50% | 31.25% | 34.38% | 9 | 1 |
| LIQE | 34.38% | 40.62% | 34.38% | 10 | 1 |
| TOPIQ | 46.88% | 53.12% | 43.75% | 7 | 2 |
| ARNIQA | 34.38% | 34.38% | 40.62% | 17 | 7 |

The rejected-winner fraction uses the same tied-winner expectation:

| Model | Square rejected winner | Inside rejected winner | Cache rejected winner |
| --- | --- | --- | --- |
| SPAQ | 21.88% | 21.88% | 21.88% |
| AVA | 25.00% | 25.00% | 25.00% |
| LIQE | 21.88% | 15.62% | 21.88% |
| TOPIQ | 12.50% | 9.38% | 12.50% |
| ARNIQA | 31.25% | 21.88% | 31.25% |

These are descriptive results across all 32 eligible units, including train and validation. The untouched test subset contains only two units:

| Model | Square test best match | Inside test best match | Cache test best match |
| --- | --- | --- | --- |
| SPAQ | 0% | 50% | 0% |
| AVA | 0% | 0% | 0% |
| LIQE | 0% | 0% | 0% |
| TOPIQ | 50% | 50% | 50% |
| ARNIQA | 0% | 0% | 0% |

## Ranking and score sensitivity

Kendall tau is the mean within-unit agreement with the corrected square baseline; baseline tau is 1. Normalized score differences use raw ranges SPAQ 100, AVA 9, LIQE 4, TOPIQ 1 and ARNIQA 1 for descriptive comparability. These are not recalibrated production score anchors.

| Model | Inside mean Kendall tau | Cache mean Kendall tau | Inside p95 absolute score delta | Cache p95 absolute score delta |
| --- | --- | --- | --- | --- |
| SPAQ | 0.543 | 0.936 | 0.0840 | 0.0094 |
| AVA | 0.541 | 0.920 | 0.1007 | 0.0051 |
| LIQE | 0.625 | 0.948 | 0.1456 | 0.0159 |
| TOPIQ | 0.622 | 0.957 | 0.0375 | 0.0102 |
| ARNIQA | 0.211 | 0.688 | 0.0770 | 0.0094 |

Cache score differences are small in magnitude but still change selected winners, particularly for ARNIQA. A small absolute delta is insufficient to declare a cache policy equivalent for culling.

The largest SPAQ/AVA/LIQE inside-fit discrepancies in landscape and portrait were visually reviewed, including square comparisons for a landscape and portrait outlier. Content, upright framing and proportions agreed; the square policy adds top/bottom or side padding. This inspection found no orientation/warping failure in those examples. It does not establish the causal reason for a model's score shift or replace human labels. Further TOPIQ/ARNIQA discrepancy review and representative strata remain follow-up work.

## Resource measurements and limits

Warm CPU inference p95:

| Model | Square p95 seconds | Inside p95 seconds | Cache p95 seconds |
| --- | --- | --- | --- |
| SPAQ | 0.907 | 0.942 | 0.936 |
| AVA | 0.857 | 0.857 | 0.844 |
| LIQE | 0.669 | 0.660 | 0.677 |
| TOPIQ | 0.553 | 0.408 | 0.557 |
| ARNIQA | 0.438 | 0.331 | 0.452 |

Median pipeline conversion was 1.228 s, shared-cache miss 0.923 s and shared-cache hit 0.074 s. Cumulative process peak RSS was 8.964 GiB; this is not per-model GPU memory. One repetition per source, a shared host with some test-process overlap and no isolated GPU measurement prevent claiming that production resource gates passed.

Inside-fit keeps aspect ratio and changes the presence of padding, but its JPEG encoding grid also differs from square encoding. This comparison does not fully separate padding from codec effects. A JPEG quality sweep, isolated pixel/tensor transforms, alternative RAW decode routes, small-subject/detail strata and greater portrait/test coverage remain necessary before adoption.

## Per-model decision and next evaluation

- SPAQ: **HOLD**; inside-fit reduced aggregate best-pick agreement. Keep square defaults and confirm on an expanded independent set.
- AVA: **HOLD**; inside-fit and cache both reduced aggregate agreement. Inside-fit p95 normalized score change exceeded 0.10; reviewed examples do not justify default promotion.
- LIQE: **HOLD**; inside-fit improved aggregate agreement and reduced rejected picks, warranting a checkpoint-specific follow-up. Portrait best-pick agreement remained zero on only two units; p95 normalized change exceeded 0.10.
- TOPIQ: **HOLD**; inside-fit improved aggregate agreement and reduced rejected picks, but the two-unit test subset did not improve. Cache agreement fell. Extend independent coverage and measure isolated GPU resources.
- ARNIQA: **HOLD**; inside-fit preserved aggregate best agreement while changing 17/32 winner sets; cache improved aggregate agreement but changed seven winner sets. These shifts require more labeled detail/portrait and reject-all evaluation.

The pre-recorded gates require representative orientation strata (at least ten labeled groups per principal orientation), square/extreme/small-subject/raster/RAW coverage, acceptable-pick and rejection checks, visual review of large deltas and isolated resource measurements. Proposed quality thresholds still need owner agreement before any promotion. No changed default is accepted here. Follow-up cache implementation remains [#406](https://github.com/synthet/image-scoring-pipeline/issues/406), input-contract documentation [#320](https://github.com/synthet/image-scoring-pipeline/issues/320), and evaluation [#570](https://github.com/synthet/image-scoring-pipeline/issues/570).

## Reproduction and artifact identity

Run from the repository root with the ignored frozen manifest and existing cached weights mounted in gpu-shell:

```powershell
docker exec image-scoring-gpu-shell python scripts/python/benchmark_scoring_inputs.py --manifest .agent/scratch/scoring-input-issues/labeled-manifest.json --output .agent/scratch/scoring-input-issues/labeled-evaluation --repeats 1 --models spaq ava liqe topiq arniqa
docker exec image-scoring-gpu-shell python scripts/python/summarize_scoring_input_benchmark.py .agent/scratch/scoring-input-issues/labeled-evaluation/results.json --output .agent/scratch/scoring-input-issues/labeled-evaluation/summary.json
```

Private outputs: `results.json`, `summary.json`, `metadata.json`, progress and prepared/cache image variants under the ignored output directory. Scripts are versioned repository artifacts; the frozen manifest and reviews stay local.

| Frozen artifact | SHA-256 |
| --- | --- |
| snapshot_sha256 | `fe26c0e7710362424e123fc42f75ad911c2b41bd468c66896e31467d4c9fe7fa` |
| sample_sha256 | `345946813ec5e84100f41937a2bc9cc9727ae27134ae65083d0ef449b109b660` |
| reviews_sha256 | `2b2967cb14bbb9534d14186d9dec5739b29292209f700aea0dfa10fdb2fe5df9` |
| benchmark_sha256 | `3c10018e8e51d413e11b201dd83e6aa326ac32335276fa6d009972b3dfe04300` |
| summary_sha256 | `eb2eb4f7c830825f06a43f6b3171722177cb0016016d6e19d765b0e3946b1b3e` |
