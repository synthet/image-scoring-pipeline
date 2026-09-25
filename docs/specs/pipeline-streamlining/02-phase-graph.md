---
type: Feature Spec
title: "Spec 02: phase graph changes"
description: Drop the keywords→scoring prerequisite, split burst grouping from pick assignment, and add an attempt-before edge so scoring consumes localization without ever being blocked by it.
resource: docs/specs/pipeline-streamlining/02-phase-graph.md
tags: [specs, pipeline, phases, dag, scoring, culling, localization]
timestamp: 2026-09-25T00:00:00Z
okf_version: 0.1
status: proposed
---

# Spec 02: phase graph changes

**Issue:** #407 · **Hub:** [INDEX.md](INDEX.md) · **Milestone:** M1

## Summary

`PHASE_PREREQUISITES` (`modules/phases.py`) contains two edges without data behind them, and lacks
one edge the target pipeline needs:

1. **`keywords` → `scoring`.** Tagging reads the thumbnail and the stored `clip_vit_b32_image`
   vector, and encodes the image itself when no vector exists
   ([keywords.md](../../architecture/pipeline/phases/keywords.md)). It never reads a score.
2. **`culling` → `scoring`.** Only pick assignment uses scores
   (`selection_policy.classify_sorted_ids` ranks by score). Burst grouping uses capture time, Apple
   burst IDs and embeddings.
3. **`localization` → `scoring`** is only a preferred-before edge today. Registered advisory edges
   are projected onto executors (`phase_executors.py`) but never drive planning. Runs execute
   stages one at a time in canonical order (`pipeline_orchestrator.py`), so co-requested
   localization already runs first. But:
   - a scoring-only submission never localizes;
   - auto-drive excludes localization entirely (`runs_autodrive.DEFAULT_TARGET_PHASES`).

   Subject-aware scoring (spec 04) needs localization *attempted* before scoring, without ever
   waiting on its success.

## Users / stakeholders

- **Operator:** tags appear without waiting for the slowest phase, and bursts are available early.
- **Scoring (spec 04):** receives a localization attempt for each image it scores.
- **Gallery:** consumes phase lists and phase codes, and is affected only if a new phase code is
  added (see [Open questions](#open-questions)).

## Product scenario

- **Tagging:** an operator submits tagging for a folder that has metadata but no scores. It runs
  immediately.
- **Scoring:** an operator submits scoring for new images while localization is enabled. The plan
  gains a localization stage for images without a current attempt. Scoring then proceeds, using
  subject crops where a box exists and full frame otherwise.
- **Detector outage:** localization records retryable failures, and scoring still completes on
  full frame.

## Non-goals

- Changing any runner's per-image selection except where stated.
- Making localization a hard prerequisite of anything.
- Adding a UI for the new edge kind.

## User stories

- As an operator, I want tagging to run right after metadata, so that keywords don't wait for
  scoring.
- As an operator, I want bursts grouped before scoring finishes, so that I can browse stacks early.
- As a scoring developer, I want scoring to see a localization attempt for every image, so that
  subject-aware scoring has an input or a recorded reason why not.

## Acceptance criteria

- **AC-1** — The phase registry shall list `metadata` as the only hard prerequisite of `keywords`.
- **AC-2** — When `pipeline_prefix_through("keywords")` is called, the registry shall return
  `["indexing", "metadata", "keywords"]`.
- **AC-3** — The phase registry shall define a `PHASE_ATTEMPT_BEFORE` table whose only initial
  entry is `localization` → (`scoring`,).
- **AC-4** — When a run plan requests a consumer listed in `PHASE_ATTEMPT_BEFORE` and the producer
  phase is enabled, the planner shall insert the producer stage ahead of the consumer if any
  in-scope image lacks a current producer attempt.
- **AC-5** — If the producer phase is disabled by its config flag, then the planner shall leave the
  plan unchanged.
- **AC-6** — The planner shall count an attempt as present when its status is `detected`,
  `no_detection`, `terminal_error` or `disabled`.
- **AC-7** — If a producer attempt is `retryable_error`, then the consumer shall run its fallback
  path for that image in the same run.
- **AC-8** — An attempt-before edge shall never cause `missing_prerequisites` to report the
  producer as missing.
- **AC-9** — When auto-drive targets `scoring` while `localization.enabled` is true, auto-drive
  shall include `localization` in the submitted plan.
- **AC-10** — Where `pipeline.culling_requires_scoring` is false, the culling runner shall group
  bursts for images that have no `score_general`.
- **AC-11** — While an image in a stack has no `score_general`, the culling runner shall leave that
  stack's pick/reject assignment pending, not neutral.
- **AC-12** — When scoring completes for a folder with pending stacks, the system shall run pick
  assignment for those stacks.
- **AC-13** — The `/api/runs/submit`, `/api/pipeline/submit`, dispatcher, auto-drive and heal paths
  shall produce identical plans for identical requests under the new edges.

## Assumptions and dependencies

- The runner already falls back to encoding the image when no reusable CLIP vector exists, so AC-1
  needs no tagging change.
- Rollout stage 4 status semantics (`detected`, `no_detection`, `terminal_error`, `disabled`,
  `retryable_error`) are used as merged in #395.
- The existing parity tests (`tests/test_phase_submission_vocabulary_parity.py` and the registry
  drift tests) are extended, not replaced.

## Open questions

1. **Split culling into two phase codes, or keep one?** The options:
   - Two codes: `culling` groups bursts, and a new `selection` assigns picks. This gives cleaner
     completeness predicates, but a new `phase_code` is a cross-repo contract change.
   - One code with a pending-picks state (AC-10 to AC-12). This keeps the contract but adds state.
   The proposal is one code first, behind `pipeline.culling_requires_scoring`, revisited after M1.
2. Should `bird_species` stay behind `keywords`? Once the cascade provides regions (spec 03), its
   scope can come from regions and a scene route instead of the `birds` keyword. That change
   belongs to rollout stage 5.

## Implementation plan

**Goal:** AC-1 to AC-13 pass. Existing plans are unchanged except for the keywords edge and the
inserted localization stage.

**Files:**
- `modules/phases.py`: the keywords edge, `PHASE_ATTEMPT_BEFORE`, and an `insert_attempt_before`
  helper.
- `modules/phase_executors.py`: project the new table as `attempt_before`.
- `modules/pipeline_orchestrator.py` and the run-submission paths: call the helper after selector
  resolution.
- `modules/runs_autodrive.py`: AC-9.
- `modules/selection_runner.py` and `modules/selection.py`: AC-10 to AC-12.
- Docs: [phase-graph.md](../../architecture/pipeline/phase-graph.md) and
  [PIPELINE_TERMINOLOGY.md](../../technical/PIPELINE_TERMINOLOGY.md).

**Approach:**
1. Keywords edge and doc update. This is a small, separately shippable PR.
2. `PHASE_ATTEMPT_BEFORE` and the planner insertion, covered by tests for every selector form.
3. Auto-drive inclusion.
4. Culling pending-picks state behind its flag.

**Tests to write first:**
- `tests/test_phase_graph_edges.py`: AC-1, AC-2, AC-3, AC-8.
- `tests/test_attempt_before_planning.py`: AC-4 to AC-7, for every localization status.
- `tests/test_runs_autodrive.py`: extended for AC-9, reusing the `_no_live_db` fixture from #336.
- `tests/test_culling_pending_picks.py`: AC-10 to AC-12.
- `tests/test_phase_submission_vocabulary_parity.py`: extended for AC-13.

**Rollback:** each change reverts independently:
- restore the `keywords` → `scoring` tuple;
- empty `PHASE_ATTEMPT_BEFORE`;
- set `pipeline.culling_requires_scoring=true`.
