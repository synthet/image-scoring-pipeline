---
type: Feature Spec
title: Evaluate aspect-preserving model inputs and gate shared-rendition scoring adoption
description: Evaluate aspect-preserving model inputs and gate shared-rendition scoring adoption
resource: planning/scoring-inputs/03-preprocessing-evaluation.md
tags: [scoring, orientation, tasks]
timestamp: 2026-10-06T04:44:10Z
okf_version: 0.2
---
# Evaluate aspect-preserving model inputs and gate shared-rendition scoring adoption

Issue: https://github.com/synthet/image-scoring-pipeline/issues/570

Resumed evaluation snapshot, 2026-10-06. Checked items have local evidence; changes remain uncommitted. GitHub issues and Project Stage are authoritative. Partial gates remain unchecked.

Behavioral context: derived from competitive analysis of a commercial application's observable behaviour and documentation; contains no code, identifiers, fitted constants or model artefacts from it. Implementation evidence and proposed changes below are from this repository and the gallery repository. Reference preview dimensions and encoding settings are not adopted as requirements.

## Problem and scope

The shared scoring preprocessor currently makes square JPEGs by aspect-preserving resize plus black padding. Models can apply further transformations. Removing padding or adopting the existing shared rendition cache changes model input content, scale, compression and potentially rankings; an orientation fix alone does not establish which input policy is best.

This task owns the scoring evaluation and adoption decision, not implementation of the shared cache already tracked in https://github.com/synthet/image-scoring-pipeline/issues/406. Depends on https://github.com/synthet/image-scoring-pipeline/issues/568 and https://github.com/synthet/image-scoring-pipeline/issues/569. Coordinate published model-input documentation with https://github.com/synthet/image-scoring-pipeline/issues/320.

## Acceptance criteria

- [ ] EV-AC-1: Establish a versioned baseline after orientation/routing fixes, using our own representative portrait, landscape and square photos, JPEG/RAW decode routes, small subjects and extreme aspect ratios. Record sampling and exclusions.
- [ ] EV-AC-2: Verify each active checkpoint's supported input contract from its upstream documentation/code before selecting alternatives. Compare current square padding against valid aspect-preserving/model-native policies. Separate orientation, resize, crop and JPEG-encoding effects.
- [ ] EV-AC-3: Measure per-model score shifts, within-burst rank/pick agreement, latency, memory and decode time. Use human labels where available; do not treat agreement with legacy scores alone as quality evidence.
- [ ] EV-AC-4: Evaluate `modules/rendition_cache.py` specifically for scoring: resolution cap, decode route, JPEG round trip, hit/miss pixel equivalence and provenance. Report which models can consume it safely and which need higher-detail input.
- [x] EV-AC-5: Define pass/hold criteria before the main benchmark; publish manifest, commands, model/policy versions, results and limitations. Promote a changed default only after the gate passes; a hold decision is a valid outcome.
- [ ] EV-AC-6: Any accepted change gets per-model configuration, cache/policy versioning, a limited rollout and targeted rerun/rollback guidance. No automatic removal of padding or full-library rescoring.

## Ordered implementation tasks

- [ ] EV-T-1: Resolve upstream input contracts, select sample strata and record acceptance thresholds before running the comparison (EV-AC-1/2/5).
- [x] EV-T-2: Build a reproducible benchmark using our decode/preprocessing code and licensed upstream weights; add focused tests for aspect preservation, policy identity and consistent source pixels (EV-AC-1/2).
- [ ] EV-T-3: Compare transformations one at a time, including cache hit/miss and full-source versus cached-source detail. Extend `tests/test_rendition_cache.py` only where a scoring adoption requirement is missing (EV-AC-2/4).
- [ ] EV-T-4: Run real-model inference, report quality/ranking and resource measurements, and inspect the largest portrait/landscape discrepancies (EV-AC-3/4).
- [x] EV-T-5: Publish a per-model adopt/hold decision and link any implementation follow-up to #406 and #320. Document policy version, affected scores and rollback before promotion (EV-AC-5/6).

## Rollout and rollback

Benchmarking does not change production defaults. An accepted policy is a separate implementation change with before/after evidence and independently reversible configuration. Existing shared-cache work continues under #406.

## Completed comparison and remaining gates

The [labeled benchmark report](BENCHMARK-RESULTS.md) freezes sample/review/script hashes, checkpoints, commands, metrics and exclusions. All five enabled models completed 1,815 measured inferences across 121 NEFs and three policies, with original hashes unchanged and exact shared-cache hit/miss decoded-pixel equivalence. Human best-pick and rejected-pick metrics are distinct from legacy rank agreement. Focused implementation/benchmark-summary validation totals **265 passing tests**; see [verification](VERIFICATION.md).

EV-AC-5, EV-T-2 and EV-T-5 are complete locally: thresholds were recorded before the comparison and every model/shared-cache default is **HOLD**. EV-AC-1/2/3/4 and EV-T-1/3/4 remain partial: only two portrait and two test groups, no square/raster/extreme-aspect strata, compound JPEG/cache effects, one cache decode route and no isolated GPU memory measurement. Contracts, CPU timings, decode/cache timings and SPAQ/AVA/LIQE discrepancy inspection are recorded; they do not satisfy all adoption gates. EV-AC-6 stays open for any future accepted policy; none was promoted. Follow-ups remain #570, #406 and #320.
