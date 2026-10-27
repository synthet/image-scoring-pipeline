---
type: Feature Spec
title: Honor per-model scoring input resolutions in local and remote registry hosts
description: Honor per-model scoring input resolutions in local and remote registry hosts
resource: planning/scoring-inputs/02-model-input-routing.md
tags: [scoring, orientation, tasks]
timestamp: 2026-10-06T04:44:10Z
okf_version: 0.2
---
# Honor per-model scoring input resolutions in local and remote registry hosts

Issue: https://github.com/synthet/image-scoring-pipeline/issues/569

Resumed implementation snapshot, 2026-10-06. Checked items have evidence in [verification](VERIFICATION.md); code remains uncommitted and not deployed. GitHub issues and Project Stage are authoritative.

Behavioral context: derived from competitive analysis of a commercial application's observable behaviour and documentation; contains no code, identifiers, fitted constants or model artefacts from it. Implementation evidence and proposed changes below are from this repository and the gallery repository. Reference preview dimensions and encoding settings are not adopted as requirements.

## Problem and evidence

`modules/pipeline.py` can generate separate LIQE and MUSIQ inputs from `scoring.model_preprocessing`, storing `_liqe_preprocess_path`. The live `MultiModelHost` iterates active models using the same `processing_path`, so the separate LIQE input is not selected there. The remote scoring proxy uploads the common input while host-local path strings cannot identify files on the GPU runner. Current selection also combines SPAQ/AVA resolution lookup instead of representing each model independently.

## Scope and dependencies

Depends on https://github.com/synthet/image-scoring-pipeline/issues/568 for the upright-source contract. Fix model-to-rendition selection locally and across the existing remote/fallback paths. Keep the current padding and decoder policy. Every variant must be derived from the same upright source rather than a smaller prepared variant. Coordinate canonical input documentation with https://github.com/synthet/image-scoring-pipeline/issues/320.

## Acceptance criteria

- [x] RT-AC-1: Enabled models receive their configured input resolution, with documented defaults when a model has no override. LIQE, SPAQ and AVA overrides remain independent; invalid values fail validation or follow explicit documented bounds.
- [x] RT-AC-2: Every model variant derives from the common upright source; changing invocation order cannot reduce the available source detail or alter selection.
- [x] RT-AC-3: Local and remote paths receive equivalent decoded pixels and policy metadata for the same model. Transfer selected rendition bytes; never require the remote host to open a client filesystem path.
- [x] RT-AC-4: Existing remote fallback behavior, legacy/default single-input requests, external score injection and inactive/shadow-model semantics remain covered. No inference replay or missing-input silent fallback is introduced.
- [x] RT-AC-5: Cache keys and result/run provenance distinguish source identity, input policy, dimensions and encoding settings. Tests inspect actual received image content/dimensions rather than only mocked path strings.

## Ordered implementation tasks

- [x] RT-T-1: Add failing `test_registry_selects_each_model_rendition` and `test_missing_override_uses_documented_default` in `tests/test_engines_wrappers.py` or focused `tests/test_scoring_preprocessing.py` (RT-AC-1).
- [x] RT-T-2: Define a model-input mapping shared by the worker and host; keep preprocessing metadata separate from external model scores. Implement source-to-variant generation and host selection in `modules/pipeline.py` and `modules/engines/host.py` (RT-AC-1/2/5).
- [x] RT-T-3: Add `test_variants_derive_from_upright_source` using distinguishable detail patterns and different resolutions; verify equal-resolution reuse only for identical policies (RT-AC-2/5).
- [x] RT-T-4: Extend the scoring transport/runner contract to carry selected rendition bytes and metadata, retaining default single-input compatibility. Update `modules/remote_gpu/proxies.py`, contract and the actual runner handler located during implementation (RT-AC-3/4).
- [x] RT-T-5: Extend `tests/test_remote_gpu_runner.py` with `test_remote_scoring_receives_model_specific_pixels` and `test_scoring_payload_needs_no_host_paths`; cover same-machine/embedded fallback in existing remote tests (RT-AC-3/4).
- [x] RT-T-6: Run focused backend/remote tests in gpu-shell, record a local-versus-remote inference sample, and update #320's input specification with the implemented behavior (RT-AC-1..5).

## Rollout and rollback

Ship independently from resize-policy experiments. Version any transport extension and test client/runner compatibility before deployment. Revert the routing change separately if needed, retain identifiable preprocessing provenance, and document which scores need a bounded rerun.

## Implementation evidence

See [verification and bounded rollout](VERIFICATION.md) and the updated [canonical model-input contract](../../technical/MODEL_INPUT_SPECIFICATIONS.md). All 265 focused backend tests passed in gpu-shell. Real model score measurements and same-machine HTTP equivalence are recorded separately from the reviewed gallery baseline. Production resize/padding/decoder defaults remain unchanged. Remaining unchecked work retains its original ownership and does not imply deployment completion.
