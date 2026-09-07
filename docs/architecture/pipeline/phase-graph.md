---
type: Technical Reference
title: Phase Graph and Prerequisites
description: The canonical phase codes, execution order, prerequisite DAG, executor registration, versions, and phase-code aliases.
resource: architecture/pipeline/phase-graph.md
tags: [pipeline, phases, dag, prerequisites, executors]
timestamp: 2026-09-01T00:00:00Z
okf_version: 0.1
---

# Phase graph and prerequisites

The structural contract: which phases exist, what order they run in, what must happen before
what, and which code object actually executes each one.

## Phase codes

`modules/phases.py:27-38`:

```python
class PhaseCode(str, Enum):
    INDEXING     = "indexing"
    METADATA     = "metadata"
    SCORING      = "scoring"
    CULLING      = "culling"
    KEYWORDS     = "keywords"
    BIRD_SPECIES = "bird_species"
```

The `str` mixin means these serialise directly to JSON and SQL. Values must match
`pipeline_phases.code` in the database, seeded from `SEED_PHASES` (`modules/phases.py:430-481`).

## Canonical order

`modules/phases.py:42-49` defines `PIPELINE_PHASE_ORDER` as
`indexing, metadata, scoring, culling, keywords, bird_species`.

This order governs display and sorting, not dependency. Two helpers use it:

- `sort_phase_codes_canonical` (`:164`) — sorts `PhaseCode` values; unknown sorts to 999.
- `phase_string_sort_key` (`:169-177`) — sorts persisted strings, special-casing `bird_species`
  to `len(PIPELINE_PHASE_ORDER)` so it always lands after `keywords`.

`sort_job_phase_rows_for_display` (`:217-237`) deliberately does **not** re-sort into canonical
order. A run stores the plan the client submitted, which need not be canonical — a
`metadata, score, tag, cluster` submission stores `keywords` before `culling`. Sorting by
canonical order would report stages in an order the run never executed, so the stored
`phase_order` wins and canonical order is only a tiebreak.

## The prerequisite DAG

This is the real dependency structure. `modules/phases.py:54-61`:

```python
PHASE_PREREQUISITES: dict[str, tuple[str, ...]] = {
    "indexing":     (),
    "metadata":     ("indexing",),
    "scoring":      ("metadata",),
    "culling":      ("scoring",),
    "keywords":     ("scoring",),
    "bird_species": ("keywords",),
}
```

```mermaid
flowchart TD
    I["indexing"]
    M["metadata"]
    S["scoring"]
    C["culling — optional"]
    K["keywords — optional"]
    B["bird_species — optional"]

    I --> M
    M --> S
    S --> C
    S --> K
    K --> B
```

**`culling` and `keywords` are siblings, not sequential.** Every older diagram in this repository
draws a straight line through them, which is wrong: you can run tagging without ever clustering,
and vice versa. Only `bird_species` sits downstream of `keywords`, because it needs the `birds`
discovery keyword to know which images are in scope.

### Transitive closure

`pipeline_prefix_through(phase)` (`modules/phases.py:187-214`) walks the DAG — it does not slice
the linear order — and returns the contiguous set of phases required to reach a target:

| Call | Result |
|---|---|
| `pipeline_prefix_through("keywords")` | `["indexing", "metadata", "scoring", "keywords"]` |
| `pipeline_prefix_through("culling")` | `["indexing", "metadata", "scoring", "culling"]` |
| unknown phase | `[phase]` unchanged |

Used by the legacy single-phase `/start` endpoints (`modules/api/routers/clustering.py:137-139`,
`modules/api/routers/tagging.py:147-149`) so a downstream phase can never be enqueued ahead of
its prerequisites. Note `culling` closure does **not** include `keywords`, and vice versa.

### Satisfaction and enforcement

`missing_prerequisites(requested, satisfied)` (`:66-99`) returns `{phase: [missing]}`. A
prerequisite counts as satisfied when it is either already complete for the scope **or**
co-requested in the same run.

`compute_satisfied_phases_for_scope(scope_paths)` (`:102-146`) aggregates
`db.get_folder_phase_summary` across the scope. A phase is satisfied when, summed over all
folders, either `total_count == 0` (nothing to gate on) or
`done + skipped >= total AND failed == 0`.

`assert_prereqs_for_scope(phase_values, scope_paths)` (`:149-161`) composes the two. An empty
dict means every requested phase can proceed. Callers choose policy: `/api/runs/submit` raises
HTTP 400, while heal records a per-folder skip and continues.

## Executors and versions

Registration happens once at startup in `modules/phase_executors.py:18-113`. Each phase binds a
`run_folder` callable and a declared `depends_on`.

| Phase | `executor_version` | `run_folder` | `depends_on` | Source |
|---|---|---|---|---|
| `indexing` | `1.0.0` | `indexing_runner.start_batch` | — | `:35-48` |
| `metadata` | `1.0.0` | `metadata_runner.start_batch` | `indexing` | `:51-64` |
| `scoring` | `5.0.0` (`SCORING_EXECUTOR_VERSION`) | `scoring_runner.start_batch` | `metadata` | `:67-73` |
| `culling` | `1.0.0` | `selection_runner.start_batch`, else `clustering_runner.start_batch` | `scoring` | `:76-89` |
| `keywords` | `1.0.0` | `tagging_runner.start_batch` | `scoring` | `:92-98` |
| `bird_species` | `BIRD_SPECIES_RUNNER_VERSION` (`1.0.0`) | `bird_species_runner.start_batch` | `keywords` | `:101-109` |

`indexing` and `metadata` register **even when their runner is `None`**, with `run_folder=None`.
That makes the phase visible in the UI with a disabled trigger. The other four register only when
a runner exists — so an unregistered phase simply cannot be launched.

`culling` prefers `SelectionRunner` and falls back to `ClusteringRunner`. The fallback produces
stacks but **no pick/reject decisions**; see [phases/culling.md](phases/culling.md).

### Why executor_version matters

`image_phase_status.executor_version` records which generation of the algorithm produced a row.
When it changes, `explain_phase_run_decision` returns `executor_version_changed` and the image is
re-queued — this is the mechanism for rolling out a model or algorithm change across an existing
library. It is deliberately independent of `APP_VERSION`.

`_get_scorer_version` (`modules/phase_executors.py:115-125`) carries an explicit warning: do not
use the per-model `shared_scorer.VERSION` here. That tag names the active backend, not the phase
generation stored in IPS.

## Phase flags

From `SEED_PHASES` (`modules/phases.py:430-481`), inserted into `pipeline_phases` on first start:

| Code | Name | `sort_order` | `optional` | `default_skip` |
|---|---|---|---|---|
| `indexing` | Indexing | 1 | 0 | false |
| `metadata` | Physical Metadata | 2 | 0 | false |
| `scoring` | Scoring | 30 | false | false |
| `culling` | Culling & Stacks | 40 | true | false |
| `keywords` | Keywords | 50 | true | false |
| `bird_species` | Bird Species | 60 | true | false |

`optional` and `default_skip` drive orchestrator planning
(`modules/pipeline_orchestrator.py:227-238`):

- An `optional` phase already marked `skipped` is dropped from the plan.
- An `optional` phase with `default_skip` and no status is written `skipped`
  (reason `default_skip`, actor `system`) and bypassed.

## Phase code aliases

The API and job payloads use shorter tokens than the DB. `modules/phases.py:240-244`:

```python
PHASE_CODE_ALIASES = {
    "score":   "scoring",
    "tag":     "keywords",
    "cluster": "culling",
}
```

`normalize_phase_codes` (`:247-270`) strips a `PhaseCode.` prefix, lowercases, applies the
aliases, dedupes, and returns canonically sorted values.

The run planner carries a wider alias set (`modules/run_phase_planner.py:24-31`), adding
`clustering` and `selection` to `culling`, `tagging` to `keywords`, and `bird-species` to
`bird_species`. The dispatcher has its own map again at `modules/job_dispatcher.py:531-538`.

### The bird_species asymmetry

`normalize_phase_codes` **explicitly drops `bird_species`** (`modules/phases.py:261`), commented
as a *"separate job type (API / job_phases), not a PhaseCode enum value"* — even though it very
much is a `PhaseCode` member. Consequently every caller must special-case it, for example
`modules/api/routers/electron_runs_lifecycle.py:65-70` strips it before normalising and
re-attaches it afterwards.

Treat this as a known wart, not a rule with a clean rationale.

## Known gaps

- **`PhaseExecutor.depends_on` is inert.** Its own docstring says *"Enforcement deferred to v2."*
  (`modules/phases.py:385`). Real gating lives in `PHASE_PREREQUISITES` plus
  `assert_prereqs_for_scope`. The two are kept in step by convention only — the comment at
  `modules/phases.py:53` asks you to keep them aligned, and nothing checks it.
- **`PipelineOrchestrator.PHASE_ORDER` is not `PIPELINE_PHASE_ORDER`.** The orchestrator list
  (`modules/pipeline_orchestrator.py:14-20`) has five entries; `bird_species` is absent, and there
  is no bird-species runner slot in its runner map (`:32-38`). The comment at
  `modules/phases.py:41` claiming they are the same order is misleading.
- **`SEED_PHASES` is inconsistently typed.** The first two rows use integers for `enabled` and
  `optional`; the last four use booleans and omit `enabled` entirely.

## Related

- [phase-preconditions.md](phase-preconditions.md) — how these prerequisites are enforced at runtime
- [phase-status-machines.md](phase-status-machines.md) — what states a phase can occupy
- [terminology-map.md](terminology-map.md) — full cross-naming table
- [phases/](phases/) — what each phase actually does
