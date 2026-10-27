---
type: Technical Reference
title: Model input specifications
description: Orientation, per-model input routing, wrapper transforms and scoring provenance.
resource: technical/MODEL_INPUT_SPECIFICATIONS.md
tags: [scoring, models, orientation]
timestamp: 2026-10-06T23:18:11Z
okf_version: 0.2
---
# Model input specifications

This describes the locally implemented scoring contract as of executor **5.2.0**. The changes are uncommitted and not deployed. Source code and configuration remain authoritative; [verification](../planning/scoring-inputs/VERIFICATION.md) records evidence and rollout limits. Related issues: [#320](https://github.com/synthet/image-scoring-pipeline/issues/320), [#568](https://github.com/synthet/image-scoring-pipeline/issues/568), [#569](https://github.com/synthet/image-scoring-pipeline/issues/569), [#570](https://github.com/synthet/image-scoring-pipeline/issues/570).

## Source and orientation

Original files supply model inputs. `PrepWorker` converts RAW sources to a full available preview JPEG; raster sources enter the scoring preprocessor directly. The conversion and direct RAW-preprocessing routes are distinct: pipeline conversion tries its existing decoder sequence, while direct preprocessing honors `raw_conversion.method`. The routing fix does not change either decoder preference.

Before resize, pad or an intermediate JPEG save, apply EXIF rotation/reflection once. Raster EXIF 1–8 is handled by Pillow. For an embedded RAW preview, a valid non-normal preview tag wins; a missing, normal or invalid preview tag falls back to numeric source orientation. Missing/invalid source orientation defaults to 1. rawpy postprocessed pixels are already upright and are not transformed again. Temporary JPEGs have upright pixels and absent/normal orientation.

Keep three dimensions distinct: stored source width/height, upright rendition width/height and final padded model canvas. EXIF 5–8 interchange upright width/height. A portrait whose pixels are already vertical can correctly have EXIF 1. Scene classification and subject head pose do not decide EXIF transforms. Original photos and sidecars are not modified by preprocessing.

## Outer preprocessing and selection

`MultiModelMUSIQ.preprocess_image()` uses bicubic inside resize without upscaling, then black padding to a square and JPEG encoding. This preserves subject proportions while changing the canvas. Removing padding or adopting the shared localization cache requires the [evaluation gates](../planning/scoring-inputs/RESEARCH-REVIEW.md).

| Configuration | Default | Contract |
|---|---|---|
| `raw_conversion.method` | `rawpy_half` | Direct RAW-preprocessing decoder preference, with existing fallback |
| `raw_conversion.max_resolution` | 512 | Default canvas edge, bounded 224–2048 |
| `raw_conversion.jpeg_quality` | 85 | Prepared JPEG quality, bounded 50–100 |
| `scoring.model_preprocessing.<model>` | no override | Positive integer or object with `resolution`; decimal strings accepted; booleans, floats and invalid values fail |

Enabled registry models, including shadows, each receive their own resolution selection. Positive resolutions are clamped to 224–2048. SPAQ, AVA, LIQE, TOPIQ and ARNIQA overrides are independent. Every variant derives from the same unresized upright source. Identical resolutions share a variant because orientation, resize, padding and encoding policy are common. Injected external scores skip image inference; disabled models do not create variants. Preprocessing failure stops scoring rather than using an unnormalized original.

For example, this selects three different JPEG canvases; it is an example, not a recommended default change:

```json
{"scoring": {"model_preprocessing": {"spaq": 512, "ava": {"resolution": 224}, "liqe": 1024}}}
```

The legacy non-registry engine still has its prior combined MUSIQ/LIQE override behavior. Independent model selection is the worker-to-`MultiModelHost`/`RemoteScoringHost` contract. Direct callers without a mapping retain the single-input interface, with original raster/RAW preparation required before inference. Validated mapped inputs bypass redundant preparation.

## Model-specific downstream preprocessing

The selected JPEG canvas is separate from the final tensor or patches.

| Model | Project adapter | Input and downstream transform | Raw score range |
|---|---|---|---|
| MUSIQ SPAQ / AVA / KonIQ / PaQ2PiQ | `modules/engines/musiq_model.py` and `scripts/python/run_all_musiq_models.py` | Encoded JPEG bytes to cached TF Hub signature; internal multiscale processing | SPAQ/KonIQ/PaQ2PiQ 0–100; AVA 1–10 |
| LIQE | `modules/liqe.py` | RGB tensor; longest edge capped at `scoring.liqe_max_dimension`, default 518; pyiqa patch processing | 1–5 |
| TOPIQ-NR | `modules/topiq.py` | RGB tensor; longest edge capped at `scoring.topiq_max_dimension`, default 1024; pyiqa metric `topiq_nr` | approximately 0–1 |
| ARNIQA | `modules/arniqa.py` | RGB tensor; longest edge capped at `scoring.arniqa.max_dimension`, default 1024; configurable `scoring.arniqa.metric`, default `arniqa` | approximately 0–1 |

Wrapper caps can shrink a configured outer input again. A LIQE 1024 px selection does not bypass its 518 px default cap. Verify installed checkpoint transforms and the ARNIQA regression head before choosing a changed policy. Enabled/shadow state comes from current `scoring.models` configuration, not historical wrapper comments.

MUSIQ's architecture supports variable sizes and aspect ratios; this is not a project instruction to feed originals without our chosen preparation policy. [Official MUSIQ source](https://github.com/google-research/google-research/blob/master/musiq/README.md). LIQE uses patch-based processing. [Official LIQE source](https://github.com/zwx8981/LIQE/blob/main/LIQE.py).

## Local, HTTP and fallback contract

The worker supplies `model_inputs[model_name] = {path, metadata}` separately from external scores. The local host validates every required selected file before inference. The HTTP proxy transfers JPEG bytes as base64 plus metadata, with `scoring_inputs_version = 1`; client filesystem paths are excluded. The HTTP schema retains this bundle, and the runner validates hashes, dimensions and orientation before model loading. Missing inputs, unsupported versions or mismatched returned input attestations fail explicitly. Embedded fallback uses the same runtime.

Transport API version is **2**. Upgrade client and GPU runner together before submitting work. An old peer is rejected by version/fingerprint checks; it cannot silently ignore the bundle. `/v1/...` endpoint names and default single-input request fields remain available within API 2. Existing fallback/replay protections are retained.

## Cache and persisted provenance

Prepared cache filenames carry `upright-v1`; identity includes absolute source path, nanosecond mtime, size, resolution, padding, resize policy, JPEG quality and decoder preference. Old unversioned cache entries are not eligible under this policy. No bulk cache deletion is required.

Mapped model results include `input` metadata: source identity, actual decode route (or explicit unknown), upright source dimensions, selected canvas dimensions, resolution, JPEG quality, resize/padding policy and SHA-256 of selected JPEG bytes. Run-managed scoring persists these metadata under `job_image_actions.after_snapshot.scoring_inputs`; local paths are omitted. Direct mapped calls return the metadata to their caller; legacy single-input calls retain their prior result shape and version identifier. The normalized `image_model_scores` schema is unchanged and does not store this mapping.

Per-model raw and normalized scores live in `image_model_scores`, with shadow status and model version; typed `images.score_spaq`/`score_ava`/`score_liqe` columns and `images.scores_json` are retired in the current PostgreSQL schema. Aggregates remain on `images`. Canonical normalization and fusion: [score_normalization.py](../../modules/score_normalization.py), [DB schema](DB_SCHEMA.md). Injected existing normalized values must retain `normalized_score` to avoid treating them as raw model outputs.

## Rollout and evaluation

Executor 5.2.0 distinguishes corrected runs. It does not automatically enqueue or rescore the library. Select a bounded affected set, export prior scores/run versions, upgrade paired runner/client, verify canaries, then submit explicitly; [verification](../planning/scoring-inputs/VERIFICATION.md) gives the procedure and rollback.

The current resize/padding/encoding defaults remain unchanged. An initial three-source pilot was followed by a [completed five-model labeled comparison](../planning/scoring-inputs/BENCHMARK-RESULTS.md) of 121 NEFs in 32 reviewed groups across square, inside-fit and shared-cache inputs. Model-specific results were mixed, with only two portrait/test groups. Production adoption is HOLD until checkpoint-specific, representative labeled quality/resource gates pass. Legacy score agreement alone is not a quality criterion.
