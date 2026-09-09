---
type: Documentation Index
title: Pipeline Architecture — Index
description: Entry point for the comprehensive backend pipeline documentation set — phases, sub-steps, transitions, preconditions, control plane, and persistence.
resource: architecture/pipeline/INDEX.md
tags: [pipeline, architecture, phases, index, okf]
timestamp: 2026-09-08T00:00:00Z
okf_version: 0.1
---

# Pipeline architecture — index

The complete graph of the **image-scoring-backend** processing pipeline: what the phases are,
what runs inside each of them, what state they can be in, what has to be true before work
happens, and which layer decides that work should happen at all.

These pages are written from source. Every claim carries a `file:line` citation so it can be
re-checked. Where code and older documentation disagree, these pages follow the code and say so
in a **Known gaps** section.

## Start here

| If you want to… | Read |
|---|---|
| Understand the system in one sitting | [overview.md](overview.md) |
| Know which phases exist and what depends on what | [phase-graph.md](phase-graph.md) |
| Debug a stuck or wrongly-`done` phase | [phase-status-machines.md](phase-status-machines.md) → [phase-preconditions.md](phase-preconditions.md) |
| Know why an image was skipped | [phase-preconditions.md](phase-preconditions.md) |
| Know what one phase actually does, step by step | [phases/](phases/) |
| Trace a run from HTTP request to database write | [run-lifecycle.md](run-lifecycle.md) |
| Understand auto-drive, JIT planning, or heal sweeps | [control-plane.md](control-plane.md) |
| Write a query against phase state | [persistence.md](persistence.md) |
| Translate between a UI label, a `phase_code`, and an endpoint | [terminology-map.md](terminology-map.md) |

## Pages

| Page | Covers |
|---|---|
| [overview.md](overview.md) | Layered architecture, the six phases, the three status vocabularies, how the pieces fit. |
| [phase-graph.md](phase-graph.md) | `PhaseCode`, canonical order, the `PHASE_PREREQUISITES` DAG, executors and versions, phase aliases. |
| [phase-status-machines.md](phase-status-machines.md) | All three state machines: per-image, per-run-stage, and the computed folder rollup. |
| [phase-preconditions.md](phase-preconditions.md) | Submit-time gating, the per-image run/skip decision, completeness predicates, work claims. |
| [run-lifecycle.md](run-lifecycle.md) | Submit → dispatch → execute → advance → complete, as sequence diagrams. Control operations. |
| [control-plane.md](control-plane.md) | `JobDispatcher`, `PipelineOrchestrator`, the JIT run planner, auto-drive, and the heal/reconcile catalog. |
| [persistence.md](persistence.md) | Tables, columns, constraints, and the folder aggregate cache. |
| [terminology-map.md](terminology-map.md) | The one-row-per-phase traversal table across every naming system. |
| [localization-rollout.md](localization-rollout.md) | Proposed eight-stage rollout for early, reusable object regions and crop-aware downstream inference. |
| [localization-rollout-supplement-2026-09-08.md](localization-rollout-supplement-2026-09-08.md) | Review evidence, implementation snapshot, and fixed defaults supporting the localization rollout. |

## Per-phase pages

| Phase | Page | Executor |
|---|---|---|
| `indexing` | [phases/indexing.md](phases/indexing.md) | `IndexingRunner` |
| `metadata` | [phases/metadata.md](phases/metadata.md) | `MetadataRunner` |
| `scoring` | [phases/scoring.md](phases/scoring.md) | `ScoringRunner` → `BatchImageProcessor` |
| `culling` | [phases/culling.md](phases/culling.md) | `SelectionRunner` (fallback `ClusteringRunner`) |
| `keywords` | [phases/keywords.md](phases/keywords.md) | `TaggingRunner` |
| `bird_species` | [phases/bird-species.md](phases/bird-species.md) | `BirdSpeciesRunner` |

## Related canonical sources

- [../../CANONICAL_SOURCES.md](../../CANONICAL_SOURCES.md) — master source-of-truth map
- [../../technical/PIPELINE_TERMINOLOGY.md](../../technical/PIPELINE_TERMINOLOGY.md) — UI label ↔ `phase_code` ↔ submit token authority
- [../../technical/PIPELINE_PHASE_RUNNERS.md](../../technical/PIPELINE_PHASE_RUNNERS.md) — prose walkthrough of runner ownership
- [../../technical/DB_SCHEMA.md](../../technical/DB_SCHEMA.md) — full schema reference
- [../../technical/API_CONTRACT.md](../../technical/API_CONTRACT.md) — REST contract
- [../pipeline-architecture.md](../pipeline-architecture.md) — short architecture summary
