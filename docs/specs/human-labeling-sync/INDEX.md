---
type: Documentation Index
title: Human labeling sync — spec hub
description: Backend side of the Vexlum mobile labeler loop — build blind label tasks from the library, push previews and tasks to an Internet labeling hub, pull annotations back and import them into Postgres, feeding the #415 human culling label set (#453).
resource: docs/specs/human-labeling-sync/INDEX.md
tags: [specs, labeling, mobile, human-labels, culling, sync, hub]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.1
status: proposed
---

# Human labeling sync — spec hub

This hub specifies the **backend's part** of the human labeling loop:

1. **The backend** (this repo) picks what to label and builds blind label tasks. It renders stripped JPEG previews and pushes tasks and previews to a hub.
2. **The labeling hub** is a small Internet service, planned for a Hetzner VM, that holds batches, leases tasks to phones and stores annotations.
3. **The mobile labeler** ([synthet/image-scoring-mobile](https://github.com/synthet/image-scoring-mobile)) downloads batches, labels them offline and uploads annotations.
4. **The backend** pulls annotations back, stores them append-only in Postgres, and projects them into the evaluation tables.

**Epic:** #453 · **Status:** proposed. Nothing is implemented in this repo yet. The mobile app and a dev hub exist on the mobile repo's branch `cursor/mobile-labeler-mvp-fc18` (commit `f4feb84`).

## Decisions already taken

| Question | Decision |
|---|---|
| Who owns the contract? | **This repo.** The mobile types (`src/types/labeling.ts`) and the dev hub's routes are provisional consumers. Once the labeling contract is published here, they follow it ([CANONICAL_SOURCES.md](../../CANONICAL_SOURCES.md), [AGENT_COORDINATION.md](../../technical/AGENT_COORDINATION.md)). |
| Who connects to whom? | **The backend only makes outbound calls.** The hub never reaches into the LAN, and the webui stays on `127.0.0.1`. |
| What leaves the machine? | **Stripped JPEG previews and opaque ids only.** Originals, RAW files, paths, filenames, EXIF/GPS, scores and database access never leave. |
| How does this relate to #415? | Mobile labeling is **another collection channel** for the [human culling label set](../../planning/human-culling-labels.md). It reuses that set's units, weights and label semantics. It does not re-sample. |
| Are annotations mutable? | **No.** Raw events are append-only. Current answers are a projection, recomputed from the events. |

## Specs

| # | Spec | What it settles |
|---|---|---|
| 01 | [Architecture](01-architecture.md) | Components, trust boundaries, data flow, image identity, failure model |
| 02 | [Task and annotation contract](02-task-and-annotation-contract.md) | `LabelTask` / `AnnotationEvent` v1, modes, blindness rules, contract changes required from mobile and hub |
| 03 | [Storage and import](03-storage-and-import.md) | `labeling` schema, Alembic ownership of `human_labels`, import idempotency, projection into `human_labels` |
| 04 | [Sync agent and rollout](04-sync-and-rollout.md) | Push/pull protocol, cursors, preview pipeline, config, milestones, tests, runbook |

## Milestones

Issues are filed once the decision register below is settled.

| Milestone | Depends on | Summary |
|---|---|---|
| M0 | — | These specs (#453) |
| M1 | M0 | Schema: an Alembic migration for the `labeling` schema, plus adopting `human_labels` without data loss. Repository functions. |
| M2 | M1 | Task builder: experiment definitions, the #415 unit source, blind preview rendering to a content-addressed cache |
| M3 | M1 | Import: pull annotations, append-only store, projection into `human_labels`, label audit reads it |
| M4 | M2, M3 | Sync agent CLI and the hub contract v1 (hub-assigned cursor, asset upload, labeler identity), with mobile/hub changes landed in their repo |
| M5 | M4 | Group culling mode on mobile (per-frame grades + best frame), for #415 parity |
| M6 | M4 | Hardening: TLS-only hub, token rotation, preview retention, runbook verified on the real hub |

M2 and M3 can run in parallel.

## Decision register (open)

| ID | Question | Recommendation | Decide by |
|---|---|---|---|
| D-1 | Which image id goes off-box? | **`images.image_uuid`**, backfilled where NULL. It is already unique (`uq_images_image_uuid`), opaque and survives re-indexing better than `images.id` ([01 §Image identity](01-architecture.md#image-identity)). | M1 |
| D-2 | How should mobile culling cover the #415 protocol (grade every frame + one best frame)? | **Add a group culling task** (one task per unit, 2–12 items) in M5. Until then, single-frame `culling` answers are stored but **not** projected into `human_labels.labels` ([02 §Culling](02-task-and-annotation-contract.md#culling-modes)). | M3 |
| D-3 | Who says which person labelled an event? | **The hub stamps `labelerId` from the authenticated token.** The backend ignores any client-supplied labeler field. | M4 |
| D-4 | How are previews delivered? | **The backend uploads JPEG bytes to the hub, keyed by SHA-256.** The hub serves them over its own URLs. No third-party URLs in production tasks. | M4 |
| D-5 | How are undo and re-answers after an upload handled? | **Latest event per (task, labeler) wins by `createdAt`**, plus an optional `supersedesAnnotationId` from mobile. No deletes on the hub ([02 §Undo](02-task-and-annotation-contract.md#undo-and-re-answers)). | M3 |
| D-6 | Should the sync agent be a CLI, a maintenance job or a webui background thread? | **A CLI first** (`scripts/labeling_sync.py`), run manually or on a schedule. Move it into the job dispatcher only if manual runs prove painful. | M4 |

## Related

- [Human culling label set](../../planning/human-culling-labels.md) (#415): sampling, semantics, `human_labels` tables, evaluation plan.
- [Remote GPU worker specs](../remote-gpu-worker/INDEX.md) (#435): the same "host is the control plane, never expose the webui" stance.
- [Spec 01: decode-once rendition](../pipeline-streamlining/01-rendition.md): the preferred source for preview pixels.
- Mobile consumer notes: [`docs/LABELING_API.md`](https://github.com/synthet/image-scoring-mobile/blob/cursor/mobile-labeler-mvp-fc18/docs/LABELING_API.md) and the dev hub [`labeling-hub/README.md`](https://github.com/synthet/image-scoring-mobile/blob/cursor/mobile-labeler-mvp-fc18/labeling-hub/README.md) in image-scoring-mobile.
