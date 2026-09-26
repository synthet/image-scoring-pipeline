---
type: Plan
title: Evidence-driven scoring and culling improvement candidates
description: Clean-room improvement candidates for evidence contracts, ranking, burst handling, calibration, caching, diagnostics, and cross-repo delivery.
resource: docs/planning/reference-workflow-improvement-candidates.md
tags: [docs, planning, scoring, culling, evidence, clean-room]
timestamp: 2026-09-25T18:00:00Z
okf_version: 0.1
status: proposed
---

# Evidence-driven scoring and culling improvement candidates

> **Status:** proposal inventory, not a backlog commitment. Promote accepted slices through the canonical project board and update API/schema authorities before implementation.

## Provenance and clean-room boundary

> derived from competitive analysis of a commercial application's observable behaviour and documentation; contains no code, identifiers, fitted constants or model artefacts from it.

This page describes outcomes and engineering practices only. It does not reproduce implementation structure, recovered thresholds, calibration tables, camera tables, private assets, or product copy. Any numeric value introduced during implementation is a starting point to be re-fitted and validated on project-owned data.

## Relationship to current plans

This proposal extends rather than replaces:

- [subject-aware culling evidence](subject-aware-culling-evidence.md), which defines the current clean-room evidence direction;
- [pipeline streamlining](pipeline-streamlining.md) and its [subject-aware scoring slice](../specs/pipeline-streamlining/04-subject-aware-scoring.md);
- [localization region scores and backfill](localization-region-scores-and-backfill.md); and
- the canonical [model roadmap](../MODEL_RECOMMENDATIONS_PIPELINES.md).

The additions below focus on contracts and operating practices that make those features trustworthy in production.

## Recommended improvements

### 1. Make evidence a versioned product contract

Store each measurement as an evidence record instead of a loose score column. A record should identify:

- what was measured and whether it applies;
- normalized value or named band;
- measurement confidence, separate from the value;
- subject/region identity and the rendition used;
- model, preprocessing, and policy revisions;
- reason codes and bounded diagnostics; and
- status: measured, unknown, not applicable, degraded, or failed.

This prevents “missing” from silently looking average and lets gallery, API, analytics, and agents render the same state. Keep human decisions and model evidence in separate fields.

**Acceptance evidence:** schema round trips; OpenAPI generation; unknown/failed cases; old-reader compatibility; gallery rendering of every status.

### 2. Separate measurement from ranking

Inference should produce reusable evidence. A versioned ranking policy should combine that evidence into a burst-relative decision. Reweighting, technical-only views, or user preferences can then run without image decode or model execution.

Persist the ranking-policy revision, source evidence revision, effective weights, fallbacks, and final reasons. A recomputation with the same inputs and revision must be deterministic.

**Why:** faster exploration, reproducible decisions, simpler A/B tests, and less pressure to overwrite raw measurements when product preferences change.

### 3. Use coarse-to-detail measurement with an explicit budget

Decode once into a canonical oriented rendition. Run broad localization and inexpensive measurements first. Request a higher-detail subject/head crop only when the evidence is ambiguous or the crop is too small for a reliable decision.

The scheduler should expose:

- why a refinement ran or was skipped;
- the cost budget and observed latency;
- the fallback result if refinement fails; and
- cache provenance for every reused rendition.

The refinement rule and resource budget must be fitted locally. Avoid fixed assumptions copied from another system.

### 4. Treat uncertainty as a ranking input

Value and confidence should remain independent. Ranking policy should be able to:

- abstain when required evidence is missing;
- reduce confidence without inventing a low quality score;
- distinguish “subject absent” from “detector uncertain”;
- distinguish “eye not visible” from “eye measurement failed”; and
- prevent failed frames from becoming representatives by accident.

Return a decision state such as confident, close call, insufficient evidence, or processing error. The gallery can then ask for review instead of overstating certainty.

### 5. Make burst boundaries explainable and editable

Time gaps remain a useful initial signal, but the boundary service should also support camera identity, filename continuity, and visual change evidence. Every split should carry reason codes and confidence.

Manual merge, split, detach, and representative choices should survive reprocessing through a stable burst fingerprint or replayable edit record. If upstream identity changes, surface an unresolved edit rather than applying it to the wrong images.

All time or similarity thresholds are project-owned starting points and must be re-fitted from labelled bursts.

### 6. Add close-call output instead of a false single winner

For each stack, emit a representative plus an ordered close-call set when evidence differences are smaller than the system can justify. The close-call decision should depend on calibrated uncertainty, not only a raw score gap.

Measure:

- whether a human choice is in the close-call set;
- representative regret within each burst;
- review time saved; and
- stability when model/policy revisions change.

### 7. Govern calibration as its own lifecycle

Keep raw evidence available and treat calibration as a versioned, monotonic mapping trained only on project-owned labels. Split evaluation by folder or event to prevent near-duplicate leakage, then stratify reports by camera family, ISO band, subject size, and scene type.

Promotion should require:

- better within-burst ordering, not merely global correlation;
- bounded regressions on important cohorts;
- stable results across resampling; and
- a reversible migration/backfill plan.

Do not import fitted tables or thresholds from competitive research.

### 8. Improve species/open-set behaviour

Species inference should support a candidate set but still compare against an open-set background so the system can abstain. Separate automatic suggestion, propagated suggestion, and user override.

Propagation inside a visually coherent burst may reduce work, but it should require compatible per-frame evidence and must never overwrite manual tags. Store why a tag propagated and the source frame.

### 9. Make caches content-addressed and explainable

Every derived artifact should bind to source identity, orientation, crop/rendition descriptor, model digest, preprocessing revision, and relevant settings. A cache hit should be inspectable in diagnostics.

Use atomic writes and validate shape/version before accepting cached output. Changing a model or preprocessing rule must invalidate affected evidence without forcing unrelated phases to rerun.

### 10. Provide an evidence-first diagnostics bundle

A bounded, redacted bundle should include:

- run and phase revisions;
- rendition descriptors;
- candidate subjects and selected-region reason;
- measurement values, confidence, applicability, and fallbacks;
- burst boundary/ranking reasons;
- cache hit/miss provenance; and
- failures and timings without private absolute paths by default.

Optional visual overlays should be generated from persisted evidence, ensuring the picture and JSON describe the same decision.

### 11. Add a production performance envelope

Define budgets for first useful results, per-frame refinement, peak memory, cache growth, and cancellation latency. Report distributions by storage type and media format. Bound concurrency by decoded-pixel memory rather than CPU count alone.

Cancellation must stop scheduling new work, finish or terminate in-flight work safely, and leave no session or phase falsely marked complete.

### 12. Make cross-repo contracts additive

Introduce new evidence fields additively through backend OpenAPI/schema authority. Gallery and skills consumers should tolerate unknown fields and explicit unknown values. UI vocabulary belongs in the design-token package.

Every rollout needs:

- backend shadow production first;
- generated client refresh;
- gallery unknown/degraded states;
- model contract and model-card update;
- agent prompt/schema update; and
- shared display-token release.

## Suggested delivery order

| Order | Slice | Reason |
|---:|---|---|
| 1 | Evidence status/confidence/provenance envelope | Removes ambiguity before adding more signals |
| 2 | Error-aware ranking and deterministic policy revision | Prevents unsafe representatives and enables replay |
| 3 | Content-addressed rendition/evidence cache | Makes refinement affordable and reproducible |
| 4 | Coarse-to-detail subject/head refinement in shadow mode | Adds the highest-value evidence with bounded cost |
| 5 | Explainable burst boundaries and durable edits | Makes grouping correctable without losing intent |
| 6 | Close-call output and gallery contract | Improves user trust before automatic actions expand |
| 7 | Calibration and open-set propagation studies | Requires project-owned labels and preceding evidence |

Order numbers are delivery sequence labels, not recovered product parameters.

## Evaluation design

Use project-owned, folder-grouped data and report:

- subject localization coverage and false-positive rate;
- evidence availability, confidence calibration, and failure rate;
- within-burst pair accuracy, representative recall, and close-call coverage;
- stability across camera/scene/subject-size cohorts;
- latency, memory, cache hit rate, and cancellation behaviour; and
- human review time and reversal rate.

Blind human labels remain the primary evaluation source. Agent-assisted labels are secondary evidence and must be identified as such. Judges used for evaluation must not see the model evidence being evaluated.

## Non-goals

- Copying a commercial implementation, its model assets, or its fitted parameters.
- Moving scoring inference into the gallery or agent prompts.
- Treating a global aesthetic score as sufficient for within-burst selection.
- Auto-deleting files based only on an experimental ranker.
- Replacing backend API/schema authority with UI-local fields.
