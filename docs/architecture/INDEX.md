---
type: Documentation Index
title: Architecture — Index
description: System overview, pipeline architecture, repository structure, and database connector design for image-scoring-backend.
resource: architecture/INDEX.md
tags: [architecture, index, pipeline, okf]
timestamp: 2026-09-01T00:00:00Z
okf_version: 0.1
---

# Architecture — index

Structural documentation for **image-scoring-backend**. For contracts and stable reference
material see [../technical/INDEX.md](../technical/INDEX.md); for the source-of-truth map see
[../CANONICAL_SOURCES.md](../CANONICAL_SOURCES.md).

## System

| Page | Purpose |
|---|---|
| [system-overview.md](system-overview.md) | Component and data-flow overview. |
| [technical-summary.md](technical-summary.md) | Compact technical summary. |
| [project-structure.md](project-structure.md) | Repository layout: entry points, modules, scripts, tests. |

## Pipeline

| Page | Purpose |
|---|---|
| [pipeline/INDEX.md](pipeline/INDEX.md) | **Comprehensive pipeline documentation set** — phases, sub-steps, transitions, preconditions, control plane, persistence. |
| [pipeline/overview.md](pipeline/overview.md) | The pipeline in one page. |
| [pipeline/phase-graph.md](pipeline/phase-graph.md) | Phase codes, order, and the prerequisite DAG. |
| [pipeline/phase-status-machines.md](pipeline/phase-status-machines.md) | The three status state machines. |
| [pipeline/phase-preconditions.md](pipeline/phase-preconditions.md) | Gating and run/skip decisions. |
| [pipeline/phases/INDEX.md](pipeline/phases/INDEX.md) | Per-phase deep references. |
| [pipeline/run-lifecycle.md](pipeline/run-lifecycle.md) | Submit through completion, as sequence diagrams. |
| [pipeline/control-plane.md](pipeline/control-plane.md) | Dispatcher, orchestrator, planner, auto-drive, heal sweeps. |
| [pipeline/persistence.md](pipeline/persistence.md) | Phase tables, columns, constraints. |
| [pipeline/terminology-map.md](pipeline/terminology-map.md) | Cross-naming traversal table. |
| [pipeline/localization-rollout.md](pipeline/localization-rollout.md) | Proposed eight-stage rollout for early localization and reusable region artifacts. |
| [pipeline-architecture.md](pipeline-architecture.md) | Short summary; routes into the set above. |

## Data layer

| Page | Purpose |
|---|---|
| [DB_CONNECTOR.md](DB_CONNECTOR.md) | Connector/transport architecture and compatibility notes. |
| [microservices_proposal.md](microservices_proposal.md) | `DbClient` abstraction roadmap (proposal). |

## See also

- [../IMAGE_PIPELINE.md](../IMAGE_PIPELINE.md) — image pipeline hub
- [../ARCHITECTURE.md](../ARCHITECTURE.md) — architecture hub
- [../technical/DB_SCHEMA.md](../technical/DB_SCHEMA.md) — schema authority
- [../INDEX.md](../INDEX.md) — full documentation index
