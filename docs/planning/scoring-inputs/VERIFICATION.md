---
type: Report
title: Scoring orientation implementation and verification
description: Corrected orientation and model input routing, measured evidence and bounded rollout.
resource: planning/scoring-inputs/VERIFICATION.md
tags: [scoring, orientation, verification]
timestamp: 2026-10-06T23:03:41Z
okf_version: 0.2
---
# Scoring orientation implementation and verification

Local implementation for [#568](https://github.com/synthet/image-scoring-pipeline/issues/568) and [#569](https://github.com/synthet/image-scoring-pipeline/issues/569), resumed 2026-10-06. Code and documentation remain uncommitted and are not deployed. Existing unrelated worktree changes and thumbnail work were preserved. No database scores, original photos or XMP were changed by these checks.

## Implemented behavior

Raster inputs apply EXIF 1–8, including reflections, before resize/pad. Embedded RAW JPEGs use their valid non-normal orientation, otherwise numeric source orientation; invalid/missing source tags default to 1. Converted JPEG pixels are upright with normal/absent orientation. rawpy output is already upright and is not rotated twice. Source dimensions never determine EXIF rotation.

The square input policy, resolution default, JPEG settings and decoder preferences remain unchanged. Square tagged originals still require normalization. A failed preparation stops inference; the worker and direct legacy scorer cannot fall back to scoring an unnormalized original. Cache keys carry `upright-v1` and source/policy/encoding identity. Scoring executor and backend version are **5.2.0**.

Registry inputs are selected independently by model. All variants derive from the same unresized upright source; equal resolutions reuse one variant. Resolution values must be positive integers or decimal strings and are bounded 224–2048. The default comes from `raw_conversion.max_resolution`, currently 512. External score injection and shadow behavior remain intact.

Local hosts validate selected bytes before inference. Remote bundles carry JPEG bytes and policy metadata, not local file paths. The HTTP schema preserves these fields and rejects incomplete/unsupported bundles before inference. The runner validates the entire bundle before loading models, and the proxy verifies returned input attestations. The HTTP regression exposed and fixed a real schema field-discard bug that a runtime-only test missed.

Run-managed scoring persists model input metadata under `job_image_actions.after_snapshot.scoring_inputs`; direct mapped calls receive it in model results. Legacy single-input results retain their prior shape and version identifier. This uses the existing JSONB run trail without a schema change. The normalized score table does not store this mapping. [Canonical input contract](../../technical/MODEL_INPUT_SPECIFICATIONS.md).

## Test evidence

The RAW conversion's actual decoder label is retained on the image job after temporary JPEG creation and included in mapped input metadata. Raster preparation records `pillow:raster`; callers lacking original decode context record `unknown` explicitly. This provenance is transferred and persisted alongside the selected-byte identity.

The following ran in `image-scoring-gpu-shell`, with the real ML dependencies available:

```powershell
docker exec image-scoring-gpu-shell python -m pytest tests/test_scoring_orientation.py tests/test_scoring_preparation_failures.py tests/test_raw_conversion_retry.py tests/test_pipeline_phase_gating.py tests/test_pipeline_registry_host_skip.py tests/test_engines_pipeline_injection.py tests/test_phases_policy.py tests/test_scoring_model_inputs.py tests/test_remote_gpu_runner.py tests/test_remote_gpu_fallback.py tests/test_remote_gpu_resilience.py tests/test_engines_wrappers.py tests/test_report_collector.py tests/test_engines_shadow_mode.py tests/test_engines_cursor.py tests/test_scoring_input_benchmark_summary.py -q --tb=short
```

**265 passed**, 11 dependency deprecation warnings. Meaningful regressions were reproduced before fixes: EXIF landmark failures, fail-open preparation, HTTP field loss, dropped run provenance and direct-registry raster preparation bypass. Direct single-input registry calls now normalize originals too; mapped inputs remain selected and validated without redundant preparation.

Coverage includes all eight raster and embedded-preview transforms, TIFF decoder behavior, native portrait EXIF 1, invalid/missing tags, mirrored square originals, already-upright rawpy, repeated normalization, old-cache exclusion, encoding-key changes, independent model pixels, invocation-order detail preservation, HTTP malformed bundles, corrupted bytes before model loading, external injection, shadows, existing fallback protections and JSON persistence of provenance.

Ruff passes for all added files and touched modules/tests. `scripts/python/run_all_musiq_models.py` retains 21 pre-existing lint findings; comparison against HEAD shows identical finding codes/messages. No unrelated cleanup was performed. This is focused validation, not a full GPU/DB integration suite.

## Real orientation and score measurements

Three owned NEFs were read without modification. Original SHA-256 values were checked before and after. Prepared raster JPEGs and full pipeline conversion were exercised. The portrait sources include a Z8 file unsupported by the installed rawpy route, exercising embedded-preview fallback.

| Sample | Source orientation | Stored preview | Upright conversion | Model canvas |
|---|---|---|---|---|
| Z8 DSC_9144 | 8 | 5392 × 3592 | 3592 × 5392 | 512 × 512 |
| Z6ii DSC_5416 | 8 | 6048 × 4024 | 4024 × 6048 | 512 × 512 |
| Z8 DSC_8696 | 1 | 5392 × 3592 | 5392 × 3592 | 512 × 512 |

Cached TF Hub SPAQ/AVA weights ran on CPU. The legacy pipeline baseline uses the same resize and floor-split padding as production; correction includes the necessary JPEG bake. These deltas are measured effects of the pipeline correction, not a claim of learned rotation invariance or pure rotation isolated from encoding.

| Sample | SPAQ legacy → corrected | AVA legacy → corrected |
|---|---|---|
| DSC_9144 | 64.5418 → 71.3252 | 4.7208 → 5.0045 |
| DSC_5416 | 77.7283 → 77.5374 | 5.6919 → 5.0808 |
| DSC_8696 | 55.8921 → 55.8921 | 5.4025 → 5.4025 |

SPAQ's order across these three unrelated photos stayed the same; AVA's changed. They are not a labeled burst, so this is not pick-quality evidence. The direct rawpy path for DSC_5416 was already upright and its legacy/corrected scores matched exactly; pipeline and direct decode routes must not be conflated.

The two corrected portrait dimensions match the gallery's previously published display verification for these exact filenames. The gallery baseline also reports image 240203 through IPC/browser preview routes. Existing gallery evidence is reviewed evidence, not a new grid/overlay test in this session. The full tagged-versus-baked grid/viewer/overlay matrix remains under [gallery #176](https://github.com/synthet/image-scoring-gallery/issues/176), with RAW thumbnail work under [#406](https://github.com/synthet/image-scoring-pipeline/issues/406)/[#418](https://github.com/synthet/image-scoring-pipeline/issues/418).

Private reproducibility artifacts remain in ignored `.agent/scratch/scoring-input-issues/real-verification/`: source manifest, prepared images, exact scores/hashes and read-only probe script. The orientation probe used the then-current 5.1.0 development version; its pixel policy is the same `upright-v1` now included in 5.2.0.

## Real local-versus-HTTP routing

Actual cached SPAQ/AVA weights processed the upright DSC_9144 conversion with different selected resolutions. A FastAPI TestClient exercised multipart upload, HTTP parameter validation, runner materialization and local model execution on the same machine.

| Model | Selected canvas | Local raw score | HTTP raw score |
|---|---|---|---|
| SPAQ | 512 × 512 | 71.33 | 71.33 |
| AVA | 224 × 224 | 3.65 | 3.65 |

Selected-byte hashes and all returned policy metadata matched exactly. Report: ignored `real-verification/routing-results.json`. This verifies the actual HTTP boundary with real weights; it is not a network or hardware benchmark of a separate GPU machine. Paired client/runner deployment is still required.

## Preprocessing pilot and adoption decision

[Research review and gates](RESEARCH-REVIEW.md) were recorded before the pilot. The three-source exploratory comparison used square512, inside512 and cache_square512 with cached SPAQ/AVA weights. Original hashes and cache hit/miss pixels matched exactly. Defaults remain **HOLD**.

| Sample | SPAQ square / inside / cache | AVA square / inside / cache |
|---|---|---|
| DSC_9144 | 71.3252 / 67.9678 / 71.4097 | 5.0045 / 4.6755 / 4.9866 |
| DSC_5416 | 77.5374 / 76.3660 / 77.7734 | 5.0808 / 4.7789 / 5.0550 |
| DSC_8696 | 55.8921 / 58.0267 / 55.6299 | 5.4025 / 5.2563 / 5.3645 |

Warm median CPU inference times were approximately 0.66–0.77 s for SPAQ inside-fit and 0.57–0.63 s for AVA inside-fit, versus 0.73–0.77 s and 0.57–0.62 s for square baseline. Three repetitions per photo are insufficient for production latency gates. Cumulative process peak RSS was approximately 8.06 GiB; this is not per-model device memory.

Cache misses took 0.71–0.80 s and hits 0.033–0.049 s; scoring conversion took 0.95–1.20 s. Cached upright canvases were 1364 × 2048, 1363 × 2048 and 2048 × 1364. The cache comparison combines decode, cap and JPEG round-trip effects and cannot attribute a score change to compression alone. Shared-cache scoring adoption remains unproven even though hit/miss equivalence passed.

The owner-supplied frozen review set has now completed: **121 unique NEFs, 32 labeled groups, five active models and three policies, 1,815 measured inferences with no failures**. Original hashes and cache hit/miss decoded pixels matched. [Full results, frozen artifact identities, exclusions and per-model decisions](BENCHMARK-RESULTS.md). Inside-fit improved aggregate LIQE/TOPIQ human-pick agreement but reduced SPAQ/AVA agreement; ARNIQA rankings changed substantially. With only five portrait photos in two groups and two test groups, all default decisions remain **HOLD**. Representative coverage, isolated transform/encoding effects and GPU resource gates remain open.

## Bounded rerun and rollback

1. Before deployment, export the selected image IDs/paths, current normalized/raw model rows, scoring executor versions, relevant configuration and existing run-action snapshots. Keep the export immutable; no model input should be silently relabeled as corrected.
2. Build an explicit affected manifest. Orientation candidates have EXIF 2–8 or RAW preview/source orientation fallback and pre-5.2 scoring; keep already-upright rawpy cases separate. Missing/invalid tags require review, not a dimension-based rewrite. Routing candidates have configured per-model overrides that differed from the common input previously supplied. Unknown historical decoder provenance is reported as unknown.
3. Start with a canary of at most 20 explicit files covering reflected/rotated raster, native portrait 1, portrait RAW, landscape RAW, available HE fallback and model overrides. Use the existing scoring-only run interface for the enumerated scope; do not launch auto-drive or library-wide validation/repair. Capture run IDs and retain the manifest.
4. Upgrade backend client and GPU runner together to API **2** before remote canaries. Old peers fail version/fingerprint checks. The bundle is version **1**, while endpoint paths remain `/v1/...`. Verify selected-byte hashes, model canvases, upright preview framing and persisted run provenance before extending to additional batches of at most 100 audited files.
5. Existing phase policy makes a known old executor version eligible when a run is explicitly submitted. This bump does not enqueue jobs. Completed legacy rows with a NULL executor may still pass existing data checks and skip; use explicit force only for audited manifest entries needing correction. Do not globally clear phase status or alter stored versions.
6. Review deltas per model and within burst, keeping corrected and old runs identifiable. Do not refit normalization anchors, change decoder/padding defaults or rewrite originals as part of this correction. Existing intentional metadata-writing behavior of a production scoring run must be selected consciously; these verification scripts never call it.
7. Roll back code and transport as a coordinated compatible pair, retaining exports, new-policy results and separate cache namespaces. Do not label old pixels/scores `upright-v1` or delete unrelated caches. Restore scores only from the preserved audited export through an explicit follow-up operation; no rollback database writes were performed here.

## Remaining acceptance boundaries

#568's orientation, idempotence, versioning, dimensions and rerun documentation have local evidence. Its full gallery/RAW-thumbnail compatibility acceptance remains open. #569's registry and transport correctness has local tests and real same-machine HTTP evidence; separate-machine deployment verification remains an operational rollout step. #570 retains checkpoint-specific quality, representative sampling and GPU-resource gates before default promotion.

## Provenance

Behavioral context: derived from competitive analysis of a commercial application's observable behaviour and documentation; contains no code, identifiers, fitted constants or model artefacts from it. Implementation evidence and measurements use this repository, the gallery repository, owner-provided photos and licensed upstream weights. Reference preview dimensions and encoding settings are not adopted as requirements.
