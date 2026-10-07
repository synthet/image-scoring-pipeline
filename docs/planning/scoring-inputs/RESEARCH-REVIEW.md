---
type: Report
title: Orientation research corrections and preprocessing evaluation gates
description: Research corrections, checkpoint constraints and gates before changing scoring inputs.
resource: planning/scoring-inputs/RESEARCH-REVIEW.md
tags: [scoring, orientation, research]
timestamp: 2026-10-06T23:03:42Z
okf_version: 0.2
---
# Orientation research corrections and evaluation gates

Reviewed the supplied `C:/Users/dmnsy/Downloads/deep-research-report.md` against our code and primary sources. The report is research input; its proposed commands and camera heuristics are not implementation instructions. Follow-up: [#570](https://github.com/synthet/image-scoring-pipeline/issues/570), [evaluation task](03-preprocessing-evaluation.md), [verification](VERIFICATION.md).

## Corrections affecting implementation

EXIF 6 means rotate stored pixels 90 degrees clockwise for display; EXIF 8 means 90 degrees counterclockwise. Reflections 2, 4, 5 and 7 also matter. Width greater than height with EXIF 6 is a normal stored representation of a portrait, not evidence that its metadata is wrong. Native portrait pixels with EXIF 1 are valid. Never rewrite original orientation using a dimension heuristic. [ExifTool EXIF enumeration](https://exiftool.sourceforge.net/TagNames/EXIF.html).

The report's claim that the Nikon D90 lacks automatic orientation recording is contradicted by Nikon's specification and Camera Control Pro documentation. Camera settings and capture sequence can affect recorded orientation; a camera model name is not a substitute for inspecting each input. [Nikon D90 announcement/specification](https://www.nikon.com/company/news/2008/0827_d90_01.html), [Nikon Camera Control Pro manual, page 25](https://download.nikonimglib.com/archive3/Jbkz900bWyt303AZV6R23D1o5r04/D-CCPRO_-022600BF-___EN-ALL___.pdf).

ExifTool metadata writes do not rotate image pixels. Use numeric `-n` reads and an actual pixel decoder/transposition step. The implementation uses Pillow EXIF transposition; it does not adopt the report's unverified pixel-rotation commands. [ExifTool FAQ, questions 6 and 20](https://exiftool.sourceforge.net/faq.html).

rawpy's default `user_flip=None` uses RAW orientation. Treat its postprocessed output as already upright, rather than reapplying source EXIF. Its explicit flip values are not the EXIF 1–8 enumeration. [rawpy Params documentation](https://letmaik.github.io/rawpy/api/rawpy.Params.html).

XMP-sidecar precedence is a separate unresolved metadata contract. This change does not override embedded orientation with arbitrary sidecar values. No original photo or sidecar metadata is rewritten.

## Active model contracts and boundaries

Production config currently enables SPAQ, AVA, LIQE, TOPIQ and ARNIQA, with no per-model preprocessing overrides. The corrected outer policy remains 512 px square, bicubic inside resize without upscaling, black padding and configured JPEG encoding. This is the selected input image; wrapper preprocessing can transform it again.

MUSIQ supports varying image sizes and aspect ratios, with multiscale processing. An inside-fit candidate is reasonable to measure, but upstream architecture support alone does not justify changing the TF Hub checkpoint's production inputs. The pilot uses the installed cached SPAQ/AVA checkpoints and our existing prediction method. [Official MUSIQ README](https://github.com/google-research/google-research/blob/master/musiq/README.md), [MUSIQ paper](https://openaccess.thecvf.com/content/ICCV2021/papers/Ke_MUSIQ_Multi-Scale_Image_Quality_Transformer_ICCV_2021_paper.pdf).

LIQE extracts 224 px patches in its upstream implementation. Our wrapper additionally caps the longest tensor dimension at `scoring.liqe_max_dimension`, default 518. Selecting a 1024 px JPEG does not mean that LIQE receives a 1024 px tensor. TOPIQ and ARNIQA wrappers currently cap at 1024. Their installed checkpoint transforms, ARNIQA dataset head, patch sampling and supported minimum dimensions must be verified individually before a production-policy comparison. [Official LIQE implementation](https://github.com/zwx8981/LIQE/blob/main/LIQE.py), [pyiqa LIQE source](https://iqa-pytorch.readthedocs.io/en/stable/_modules/pyiqa/archs/liqe_arch.html).

For the labeled extension, installed **pyiqa 0.1.16** code/config was inspected directly. LIQE uses its KonIQ checkpoint, requires both sides at least 224 and selects deterministic patch indices in evaluation mode. TOPIQ-NR uses `cfanet_nr_koniq_res50`; the forced 384 square resize applies to the Swin branch, not this ResNet50 configuration. ARNIQA uses the KonIQ regression head and normalized full-size/half-size features. All candidate inside512 images are checked through the installed project wrappers; rejection is reported as a failed input rather than silently padded. Cached checkpoint assets are available; benchmark downloads are refused.

## Gates recorded before the pilot

The pilot is an engineering measurement, with an automatic HOLD on default changes. It covers the two real portrait NEFs and one landscape NEF already used for orientation verification. It excludes square/extreme-aspect inputs, JPEG source routes, small-subject strata, labeled burst picks, LIQE/TOPIQ/ARNIQA quality comparisons and per-model GPU memory. The three photos are not treated as one burst.

The main benchmark needs a versioned manifest covering portrait, landscape, square, extreme aspect ratio, small subjects, raster and RAW decode routes, with at least ten labeled bursts per principal orientation and documented exclusions. Freeze human preferred picks before model comparison. Proposed review gates, requiring owner agreement before promotion:

- No orientation, reflection, crop-coordinate or cache hit/miss pixel mismatch.
- No increase in clearly rejected human picks; at least 95% agreement with acceptable human top picks overall, with no orientation stratum declining by more than two percentage points against the corrected baseline. Report uncertainty for small strata; insufficient labels means HOLD.
- Report normalized score deltas, within-burst ranks and top-pick changes. A 95th-percentile absolute normalized delta above 0.10 triggers visual review; agreement with legacy scores is not itself evidence of quality.
- Warm inference 95th-percentile latency at most 1.2 times baseline and peak device memory at most 1.25 times baseline, or an explicitly approved resource tradeoff. Record decode time separately from inference and cache hit time.
- Each active checkpoint passes its own input-contract and quality gates before its default changes. No whole-library rescoring or cross-model default switch.

## Reproducible pilot

Runner: [benchmark_scoring_inputs.py](../../../scripts/python/benchmark_scoring_inputs.py). It reads only explicitly listed originals, uses cached TF Hub weights without downloading, and writes variants/results to the specified output directory. It does not write database scores, XMP or configuration.

```powershell
docker exec image-scoring-gpu-shell python scripts/python/benchmark_scoring_inputs.py --manifest .agent/scratch/scoring-input-issues/real-verification/pilot-manifest.json --output .agent/scratch/scoring-input-issues/policy-pilot --repeats 3
```

Compare square512 versus inside512 from the same upright source at the same JPEG quality. Compare cache_square512 as a separate exploratory compound change: the localization decode route, 2048 px cap and JPEG-90 round trip can all differ from the scoring source. Cache hit/miss pixels must match exactly. Record cold/warm inference time and cumulative process RSS; do not describe cumulative RSS as per-model GPU memory.

The local manifest and outputs contain private photo paths and remain ignored scratch artifacts. Publish aggregate measurements and limitations in [verification](VERIFICATION.md), not private originals.

## Provenance

Behavioral context: derived from competitive analysis of a commercial application's observable behaviour and documentation; contains no code, identifiers, fitted constants or model artefacts from it. Implementation and measurements use this repository, the gallery repository, owner-provided photos and licensed upstream weights. Reference preview dimensions and encoding settings are not adopted as requirements.

## Completed owner-labeled follow-up

The supplied frozen review set produced a completed five-model comparison of 121 NEFs across 32 eligible labeled groups and three preprocessing policies. [Results and reproducibility](BENCHMARK-RESULTS.md) preserve splits, independent blocks, artifact hashes and exclusions. All default decisions are HOLD: mixed checkpoint effects, two portrait groups, two test groups, compound encoding/cache changes and missing isolated GPU resource evidence prevent adoption. Proposed gate thresholds remain subject to owner agreement before promotion.
