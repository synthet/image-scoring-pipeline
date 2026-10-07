---
type: Implementation Plan
title: Resume plan for scoring orientation and model inputs
description: Completed baseline, remaining work and ordered resume steps for scoring inputs.
resource: planning/scoring-inputs/NEXT-STEPS.md
tags: [planning, scoring, orientation]
timestamp: 2026-10-06T12:00:00Z
okf_version: 0.2
---
# Next steps for scoring orientation and model inputs

Resumed 2026-10-06 from the supplied plan and research report. Orientation and registry-input routing are implemented locally and pass focused checks; changes remain uncommitted and not deployed. See [verification](VERIFICATION.md) and [research corrections/gates](RESEARCH-REVIEW.md).

## Completed baseline

The supplied session record, `D:/Projects/image-scoring-gallery/codex-session-01a10f45-e173-74c1-a514-5e1591ef0d3e.md`, and published commits establish the display/export baseline:

- [Gallery fix 63e7b2c](https://github.com/synthet/image-scoring-gallery/commit/63e7b2c0142abb606d4f51cb09b4e916d6246109): browser JPEG orientation applied once, RAW source-orientation fallback, numeric EXIF extraction, and upright exported JPEGs with normal orientation metadata.
- [Gallery documentation e677d15](https://github.com/synthet/image-scoring-gallery/commit/e677d152bf584968af9d169446855be7872ee707): [solution and verification](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/05-jpeg-export-exif-orientation.md).
- [Backend raster-thumbnail fix 0276699](https://github.com/synthet/image-scoring-pipeline/commit/02766990f3a16e93f96f61bce132dacfe2fe8c19): raster thumbnail pixels are EXIF-transposed. RAW thumbnail generation and quality-scoring preprocessing remain separate work.

The supplied record reports 56 gallery tests and one backend thumbnail test passing, upright real RAW previews through IPC and browser extraction, unchanged source/thumbnail hashes for image 240203, and repair of 41 generated JPEG thumbnails. These are previously recorded results reviewed in this session; the tests were not rerun here. They do not establish completion of scoring normalization or the full thumbnail/overlay compatibility matrix.

## Remaining sequence

1. Extend the [completed labeled comparison](BENCHMARK-RESULTS.md) under #570: add at least ten labeled groups per principal orientation, square/extreme-aspect and raster/alternative RAW decode strata, small-subject/detail examples, and independent validation/test coverage. Evaluate all-reject groups separately. Isolate padding/resize from JPEG encoding and measure per-model GPU memory/latency before any default promotion. Prioritize checkpoint-specific LIQE/TOPIQ inside-fit follow-up; all models and shared-cache scoring remain HOLD.
2. Review the local orientation/routing changes under #568/#569. Tests already cover all EXIF transforms, reflection, native portrait 1, cache identity, common-source model variants, HTTP schema/bytes, existing fallback protections and persisted run provenance. Separate-machine remote deployment is still a rollout check.
3. Complete the remaining gallery legacy-tagged versus baked thumbnail, asymmetric grid/viewer/overlay matrix under [#176](https://github.com/synthet/image-scoring-gallery/issues/176). Reuse the published extraction/export baseline. Coordinate RAW thumbnail double-tag handling with backend #406/#418; leave separate gallery score input-mode readers open.
4. Package orientation correction and routing for review without including unrelated worktree changes. The input contract is updated for #320; focused evidence is in VERIFICATION.md. Keep the resize/cache experiment independently reversible.
5. Commit/push was authorized on 2026-10-06. Publish the scoped orientation/routing and benchmark changes on `fix/scoring-upright-model-inputs`, preserving unrelated edits and staged renames. Transition the issues to In Progress on the first commit through the stage harness; retain the remaining acceptance gates and do not close them merely because local tests pass.
6. Before deployment, upgrade backend client and GPU runner together to transport API 2; verify health/fingerprints and actual selected input attestations. Use the bounded canary procedure in VERIFICATION.md, then batches of at most 100 explicitly audited affected files. No automatic library rescore, original metadata rewrite or policy-default switch.

## Current verification and tracking

The complete focused backend suite passed **265 tests** in gpu-shell, including ML-dependent orientation tests. Added benchmark-summary checks separately validate human-pick agreement, tied winners and failed-input denominators. Real SPAQ/AVA weights produced identical local/HTTP results for 512 px and 224 px selected inputs. The completed five-model labeled benchmark preserved original hashes and exact cache hit/miss pixels across 121 NEFs. All 1,815 measured inferences succeeded; [results and exclusions](BENCHMARK-RESULTS.md) retain HOLD for every model/default.

Backend #568/#569/#570 are claimed on Project 1 through the compiled harness, with no first commit yet. Checklists distinguish locally verified criteria from the remaining gallery and representative evaluation gates. All local changes remain uncommitted; unrelated edits were preserved. The authorized GitHub credential remains in ignored .env and is never included in documentation or commits.

Final verification uses scoped documentation lint; the broader wiki has unrelated existing lint failures.

## Provenance

Behavioral context: derived from competitive analysis of a commercial application's observable behaviour and documentation; contains no code, identifiers, fitted constants or model artefacts from it. Implementation evidence and proposed changes are from this repository and the gallery repository. Reference preview dimensions and encoding settings are not adopted as requirements.
