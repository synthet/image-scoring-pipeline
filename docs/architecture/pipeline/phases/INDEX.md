---
type: Documentation Index
title: Pipeline Phases — Index
description: Per-phase deep references for the six backend pipeline phases.
resource: architecture/pipeline/phases/INDEX.md
tags: [pipeline, phases, index, okf]
timestamp: 2026-09-01T00:00:00Z
okf_version: 0.1
---

# Pipeline phases — index

One page per phase. Each follows the same shape: purpose, executor and version, prerequisites,
sub-steps as a flowchart, models and algorithms, completeness predicate, what it writes, failure
and skip semantics, config keys, and known gaps.

| Order | Phase | Page | Executor | Optional |
|---|---|---|---|---|
| 1 | `indexing` | [indexing.md](indexing.md) | `IndexingRunner` | no |
| 2 | `metadata` | [metadata.md](metadata.md) | `MetadataRunner` | no |
| 3 | `scoring` | [scoring.md](scoring.md) | `ScoringRunner` | no |
| 4 | `culling` | [culling.md](culling.md) | `SelectionRunner`, fallback `ClusteringRunner` | yes |
| 5 | `keywords` | [keywords.md](keywords.md) | `TaggingRunner` | yes |
| 6 | `bird_species` | [bird-species.md](bird-species.md) | `BirdSpeciesRunner` | yes |

`culling` and `keywords` are **siblings** under `scoring`, not sequential — see
[../phase-graph.md](../phase-graph.md).

## Cross-cutting pages

- [../overview.md](../overview.md) — how the phases fit together
- [../phase-graph.md](../phase-graph.md) — order, prerequisites, executors
- [../phase-status-machines.md](../phase-status-machines.md) — status values and transitions
- [../phase-preconditions.md](../phase-preconditions.md) — run/skip decisions and completeness
- [../persistence.md](../persistence.md) — tables each phase writes
- [../INDEX.md](../INDEX.md) — the full set
