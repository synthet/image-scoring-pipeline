---
type: Implementation Plan
title: Resume plan for scoring orientation and model inputs
description: Completed baseline, remaining work and ordered resume steps for scoring inputs.
resource: planning/scoring-inputs/NEXT-STEPS.md
tags: [planning, scoring, orientation]
timestamp: 2026-10-13T00:58:42Z
okf_version: 0.2
---
# Next steps for scoring orientation and model inputs

Orientation and registry-input routing merged through
[PR #573](https://github.com/synthet/image-scoring-pipeline/pull/573) at `78029b9`.
The recorded merged-tree verification was 287 focused tests and eight CI checks.
#569 is closed; #568 remains open for representative gallery/RAW acceptance and
#570 for evaluation/adoption gates. See [verification](VERIFICATION.md) and
[research corrections/gates](RESEARCH-REVIEW.md). Code delivery is complete;
remaining rollout checks do not authorize an automatic library rescore.

## Completed baseline

The supplied session record, `D:/Projects/image-scoring-gallery/codex-session-01a10f45-e173-74c1-a514-5e1591ef0d3e.md`, and published commits establish the display/export baseline:

- [Gallery fix 63e7b2c](https://github.com/synthet/image-scoring-gallery/commit/63e7b2c0142abb606d4f51cb09b4e916d6246109): browser JPEG orientation applied once, RAW source-orientation fallback, numeric EXIF extraction, and upright exported JPEGs with normal orientation metadata.
- [Gallery documentation e677d15](https://github.com/synthet/image-scoring-gallery/commit/e677d152bf584968af9d169446855be7872ee707): [solution and verification](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/05-jpeg-export-exif-orientation.md).
- [Backend raster-thumbnail fix 0276699](https://github.com/synthet/image-scoring-pipeline/commit/02766990f3a16e93f96f61bce132dacfe2fe8c19): raster thumbnail pixels are EXIF-transposed. RAW thumbnail generation and quality-scoring preprocessing remain separate work.

The supplied record reports 56 gallery tests and one backend thumbnail test passing, upright real RAW previews through IPC and browser extraction, unchanged source/thumbnail hashes for image 240203, and repair of 41 generated JPEG thumbnails. These are previously recorded results reviewed in this session; the tests were not rerun here. They do not establish completion of scoring normalization or the full thumbnail/overlay compatibility matrix.

## Remaining sequence

1. Extend the [completed labeled comparison](BENCHMARK-RESULTS.md) under #570: add at least ten labeled groups per principal orientation, square/extreme-aspect and raster/alternative RAW decode strata, small-subject/detail examples, and independent validation/test coverage. Evaluate all-reject groups separately. Isolate padding/resize from JPEG encoding and measure per-model GPU memory/latency before any default promotion. Prioritize checkpoint-specific LIQE/TOPIQ inside-fit follow-up; all models and shared-cache scoring remain HOLD.
2. Finish #568's unchecked representative/gallery acceptance. The merged implementation already covers EXIF transforms, reflection, native portrait 1, cache identity, model-specific inputs, HTTP schema/bytes, fallback protections and provenance. Verify the running client/runner contract on the actual remote machine before a new canary; do not reimplement the merged #569 routing fix.
3. Complete the remaining gallery legacy-tagged versus baked thumbnail, asymmetric grid/viewer/overlay matrix under [#176](https://github.com/synthet/image-scoring-gallery/issues/176). Reuse the published extraction/export baseline. Coordinate RAW thumbnail double-tag handling with backend #406/#418; leave separate gallery score input-mode readers open.
4. Keep new resize/cache evaluation changes separate and independently reversible. The orientation/routing implementation and benchmark evidence are already reviewed and merged; packaging, pushing the old branch and moving its first commit to In Progress are completed work.
5. Track new #568/#570 acceptance evidence through the GitHub Project board. Reconcile current issue criteria and runtime observations before claiming deployment; historical “uncommitted/Claimed” instructions below are superseded by #573.
6. Before deployment, upgrade backend client and GPU runner together to transport API 2; verify health/fingerprints and actual selected input attestations. Use the bounded canary procedure in VERIFICATION.md, then batches of at most 100 explicitly audited affected files. No automatic library rescore, original metadata rewrite or policy-default switch.

## Current verification and tracking

The complete focused backend suite passed **265 tests** in gpu-shell, including ML-dependent orientation tests. Added benchmark-summary checks separately validate human-pick agreement, tied winners and failed-input denominators. Real SPAQ/AVA weights produced identical local/HTTP results for 512 px and 224 px selected inputs. The completed five-model labeled benchmark preserved original hashes and exact cache hit/miss pixels across 121 NEFs. All 1,815 measured inferences succeeded; [results and exclusions](BENCHMARK-RESULTS.md) retain HOLD for every model/default.

The original October 6 measurements above are retained evidence, not tests rerun
by this documentation refresh. The implementation commit `9c8525b` and PR #573
are in `master`; #569 is closed. #568's full gallery/representative acceptance
and #570's quality/resource gates remain open. Unrelated research and release
edits are not part of that delivered change.

## Related localization work

PR #594 subsequently merged active-selection species routing, the strict floor,
an ExifTool timeout retry and shadow cascade persistence. The small-crop species
gate failed (0.8123 < 0.85); those changes do not promote shared-rendition scoring,
crop IQA or new model defaults. See [the current handoff](../../../NEXT_STEPS.md)
and [gate report](../../reports/localization-agent-panel-gates-2026-10-12.md).

Final verification uses scoped documentation lint; the broader wiki has unrelated existing lint failures.

## Provenance

Behavioral context: derived from competitive analysis of a commercial application's observable behaviour and documentation; contains no code, identifiers, fitted constants or model artefacts from it. Implementation evidence and proposed changes are from this repository and the gallery repository. Reference preview dimensions and encoding settings are not adopted as requirements.
