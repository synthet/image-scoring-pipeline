---
type: Architecture Plan Supplement
title: Early Localization Rollout — Review Supplement
description: Evidence, implementation snapshot, and resolved design details supporting the refined eight-stage localization rollout.
resource: architecture/pipeline/localization-rollout-supplement-2026-09-08.md
tags: [pipeline, architecture, localization, bird-detection, rollout, review]
timestamp: 2026-09-08T00:00:00Z
okf_version: 0.1
status: proposed
---

# Early localization rollout — review supplement

This supplement preserves the September 8 review context behind
[localization-rollout.md](localization-rollout.md). The main plan is the implementation authority;
this page records the evidence and current-code observations that explain its refinements.

## Review outcome

The eight-stage structure remains appropriate: stabilize the control plane, add generic
persistence, establish deterministic renditions and crops, run localization in shadow mode,
migrate BioCLIP, evaluate other consumers, expand repair/backfill, and retire compatibility paths.

The review changed five parts of the design:

1. Shadow localization must not dual-write `images.bird_bbox`. That column participates in current
   bird-species completeness and work selection, so writing it would change production behavior.
2. Retryable outcomes are attempts but are not complete artifacts. They remain failed and repairable
   while independent full-frame phases continue.
3. A bounded repair lane is required when shadow localization ships, rather than waiting until the
   later broad-backfill stage.
4. Imported legacy boxes have unknown detector and rendition provenance. Current image metadata
   cannot safely reconstruct the historical orientation or decode route.
5. Detector promotion needs a missed-detection cohort. Positive-box-only studies cannot measure the
   size-dependent recall failure documented in the September 7 audit.

## Current implementation snapshot

The working tree already contains uncommitted Stage 1 work across phase vocabulary, API submission,
executor registration, orchestration, auto-drive, selection continuation, and healing. Treat those
changes as an implementation candidate that still has to pass the Stage 1 gate; do not reimplement
them blindly or overwrite unrelated edits.

Observed improvements include:

- `bird_species` remains in canonical `PhaseCode` normalization;
- executor prerequisites derive from `PHASE_PREREQUISITES`;
- a shared phase-to-job-type map replaces several hand-written routing maps; and
- `/api/pipeline/submit` now performs a folder-path prerequisite check.

Observed gaps remain:

- prerequisite evaluation does not yet cover all resolved selector forms consistently;
- co-requested prerequisite membership does not itself prove valid execution order;
- delegated culling follow-ups do not yet propagate child outcomes to their parent; and
- the current selection-runner candidate marks delegated parent stages `skipped`, which avoids a
  false `completed` state but is not the planned linked lifecycle.

The intended parent/child contract is: persist the link, leave delegated parent work unfinished,
and propagate child success, failure, or cancellation. A failure to enqueue the child must remain a
visible parent-stage failure.

## Verification snapshot

The following focused command was run against the existing dirty working tree:

```powershell
.venv\Scripts\python.exe -m pytest -q `
  tests/test_phase_prerequisites_registry_sync.py `
  tests/test_phase_prereq_gating.py `
  tests/test_run_submit_prereq_gating.py `
  tests/test_selection_runner_phases.py
```

Result: **43 passed, 2 failed**. Both failures are in
`tests/test_selection_runner_phases.py` and expect a delegated parent `bird_species` stage to be
marked `completed` before the child runs:

- `test_selection_runner_enqueues_bird_species`
- `test_parent_job_bird_species_phase_marked_completed`

Those expectations preserve the old UI-completeness shortcut and conflict with the refined linked
outcome contract. Implementation of Stage 1 should replace them with tests for child success,
failure, cancellation, enqueue failure, and restart recovery. The two failures are evidence about
the current uncommitted candidate, not a clean-baseline test result.

## Persistence details to retain during implementation

- Treat localization attempts as immutable history and retry scheduling as mutable queue state.
- Commit an attempt and all of its regions atomically.
- Publish an attempt as current only when its source, detector, configuration, and rendition
  identities still match. If the source changes during inference, retain the old attempt as
  superseded history and leave the new identity eligible.
- Store a run row for `no_detection`; an empty `image_regions` set has no standalone meaning.
- Preserve the original legacy JSON payload, including malformed or unknown shapes, for exact
  compatibility output.
- Allow normalized crops from imported geometry only after dimensions and orientation are verified.
- Keep full-frame and crop embeddings in distinct identities; existing BioCLIP embeddings whose
  input mode cannot be recovered are legacy artifacts.

## Detector evidence and benchmark requirements

The [September 7 recall audit](../../reports/bird-detection-recall-2026-09-07.md) examined one
59-frame bald-eagle set. Twenty frames had real boxes and 39 had `{"detected": false}` even though a
bird was visible in every frame. Detected median subject area was 0.0590 of the frame; estimated
missed median area was 0.0140. The likely mechanism is the 5392-pixel source being reduced to
`imgsz=640`, with textured backgrounds as a possible contributor. One accepted box covered 93% of
the image.

This evidence establishes a regression slice, not a general recall rate or a safe area threshold.
The Stage 3 benchmark should compare the current 640-pixel path with 1280-pixel and targeted
second-pass candidates on pinned positives, verified negatives, small subjects, textured
backgrounds, and multiple species. Record recall, false positives, latency, GPU memory, and
near-full-frame geometry. Keep production detector defaults until that benchmark is reviewed.

## Fixed defaults from the refinement

- All localization flags remain off initially.
- Shadow localization covers images indexed after a persisted enablement boundary plus images whose
  source identity changes.
- Shadow mode writes only normalized localization artifacts and diagnostics.
- Automatic repair permits three attempts per artifact identity, with one-minute and five-minute
  delays after the initial failure.
- Repair admission is limited to one job while core work is idle.
- `max_regions_per_class` initially uses the detector's existing cap of 10; consumers retain their
  own lower caps.
- Multi-region BioCLIP, broad legacy backfill, and authoritative crop/fusion outputs remain disabled.
- Physical removal of `images.bird_bbox` is outside this rollout and requires a later migration.

## Implementation handoff

Before Stage 1 code changes continue, preserve the existing dirty worktree and review diffs at the
symbol level. Complete the parent/child lifecycle and selector-aware prerequisite logic, then run
the focused phase suites plus orchestrator, auto-drive, healing, and selection integration tests.
Only after those pass should the normalized schema and compatibility reader be introduced.

