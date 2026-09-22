---
type: Report
title: Localization rollout stage 1 — control-plane consolidation
description: Completion report for stage 1 of the early-localization rollout; records what landed, one finding that reversed a planned change, and the two items carried forward.
resource: reports/localization-stage1-control-plane-2026-09-22.md
tags: [pipeline, localization, control-plane, phases, rollout, report]
timestamp: 2026-09-22T00:00:00Z
okf_version: 0.1
---
# Localization rollout stage 1 — control-plane consolidation

**Date:** 2026-09-22 · **Epic:** [#345](https://github.com/synthet/image-scoring-backend/issues/345) · **Status:** exit gate met, two items carried forward

Stage 1 of [localization-rollout.md](../architecture/pipeline/localization-rollout.md) is the
rollout's own gate: a seventh phase must not be introduced until one registry is authoritative and
every submission surface agrees on vocabulary, selector scope, ordering and prerequisite policy.

Most of it landed earlier under [#346](https://github.com/synthet/image-scoring-backend/issues/346)
(PRs #350, #352, #353, #354). This report covers the remainder — issues #364–#367, merged as
[PR #369](https://github.com/synthet/image-scoring-backend/pull/369).

## What landed

| Issue | Change |
|---|---|
| #364 | `PHASE_PREFERRED_BEFORE` beside `PHASE_PREREQUISITES`; `preferred_before` beside `PhaseExecutor.depends_on` |
| #365 | `/api/bird-species/start` expands its dependency prefix and sets `phase_code` |
| #366 | `JOB_TYPE_TO_PHASE` / `phase_for_job_type`; two duplicate maps now delegate |
| #367 | Cross-surface vocabulary parity test; DB-dependent test fixed; architecture docs resynced |

### The edge split (#364)

The registry had one edge table and one executor field, both expressing *blocking* edges. The
epic's central contract — localization artifacts are **preferred inputs, not hard prerequisites** —
had nowhere to live.

`PHASE_PREFERRED_BEFORE` is deliberately **not** read by `missing_prerequisites` or
`pipeline_prefix_through`: those decide whether work is *blocked*, and a soft edge never blocks. It
ships empty; `localization` populates it in stage 4. To keep that from being untested scaffolding,
the tests inject the stage-4 shape and assert the contract (never gates, never enters the prefix)
rather than leaving it as a comment.

## Finding: three of the four `/start` endpoints were not a gating hole

Issue #365 was originally filed claiming all four dedicated `/start` endpoints bypass the Gate 1
prerequisite check. **They do not, in any meaningful sense**, and the planned change was reversed
after measurement.

`missing_prerequisites` counts a prerequisite listed *earlier in the same plan* as satisfied. These
endpoints write `pipeline_prefix_through(<phase>)` into `job_phases`, so their effective plan always
contains every prerequisite ahead of the phase that needs it. Measured on an empty scope:

```text
scoring       ['indexing','metadata','scoring']                            -> {}
keywords      ['indexing','metadata','scoring','keywords']                 -> {}
culling       ['indexing','metadata','scoring','culling']                  -> {}
bird_species  ['indexing','metadata','scoring','keywords','bird_species']  -> {}
```

A gate over the expanded prefix can therefore never reject — it would be dead code. Gating on the
*single requested* phase instead would reject a brand-new folder from `/scoring/start`
(`{"scoring": ["metadata"]}` on an unindexed scope) and break the point-at-a-folder-and-press-Score
workflow that prefix expansion exists to support.

These endpoints are **prefix-expanding rather than plan-validating** — a legitimate second contract,
now recorded in [phase-preconditions.md](../architecture/pipeline/phase-preconditions.md) as the
*"explicitly documented as unsupported"* half of the stage 1 exit gate.

The one real divergence was `/api/bird-species/start`, which queued `["bird_species"]` alone with
`phase_code=None` — a run plan naming no upstream stage at all. It now expands its prefix like its
three siblings.

A planned shared `resolve_gate_paths` / `check_scope_prereqs` helper extraction was reverted with
the gate, since it would have had exactly one caller.

## Documentation was factually stale, not merely thin

[phase-graph.md](../architecture/pipeline/phase-graph.md) carried three false claims, all fixed in
`e5e50a1` but never resynced:

- a *"The bird_species asymmetry"* section describing a wart `normalize_phase_codes` no longer has;
- *"`depends_on` … kept in step by convention only — nothing checks it"* — it is derived from
  `PHASE_PREREQUISITES` and `tests/test_phase_prerequisites_registry_sync.py` fails on drift;
- *"`PipelineOrchestrator.PHASE_ORDER` … has five entries"* — it is `list(PIPELINE_PHASE_ORDER)`.

## Verification

- Focused control-plane suites: **182 passed**.
- The parity suite was **mutation-verified**: reintroducing the pre-#346 "drop the `bird_species`
  string" wart fails exactly two of its cases.
- `db_legacy.job_type_for_phase_dispatch` confirmed byte-identical against the old implementation
  across every phase code plus `cluster` / `clustering` / `""` / `None` / unknown.
- Regression check on isolated `git archive` exports with an identical command: `master` failed 27,
  the branch failed 20, **branch-only set empty**.

One test was fixed in passing:
`test_narrowing_to_bird_species_only_returns_a_response` carried no `db` marker but reached live
PostgreSQL through `db.build_validation_repair_plan`, so the documented fast subset failed whenever
the database was **down**.

## Carried forward

- **Delegated parent/child lifecycle** ([#368](https://github.com/synthet/image-scoring-backend/issues/368)).
  `modules/selection_runner.py` still marks the parent's remaining stages `skipped` and completes it
  regardless of the child's outcome. The planned contract needs a durable link column and DB-backed
  recovery tests, so it is scheduled with schema work.
- **`JobDispatcher.runner_map` stays hand-written.** It binds live runner *instances*, which the
  registry cannot supply. A drift test guards it instead: every `PhaseCode` value, every
  `PHASE_TO_JOB_TYPE` value and every `PHASE_CODE_ALIASES` key must be a `runner_map` key.

## Related

- [localization-rollout.md](../architecture/pipeline/localization-rollout.md) — the plan
- [localization-stage2-normalized-persistence-2026-09-22.md](localization-stage2-normalized-persistence-2026-09-22.md) — the next stage
- [phase-graph.md](../architecture/pipeline/phase-graph.md), [phase-preconditions.md](../architecture/pipeline/phase-preconditions.md)
