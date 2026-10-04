---
type: Documentation Index
title: Remote GPU worker — spec hub
description: Specs, milestones and decision register for running every GPU pipeline phase on a LAN worker that fetches images from the host and writes results directly to Postgres, with XMP synced back through a host outbox (#435).
resource: docs/specs/remote-gpu-worker/INDEX.md
tags: [specs, remote-worker, gpu, postgres, xmp, architecture]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.2
status: proposed
---

# Remote GPU worker — spec hub

This hub designs a **remote GPU inference worker**: a separate Docker app on a LAN machine with a GPU.

- **What it does:** it consumes images from the host through an authenticated API, runs the GPU pipeline phases, and writes results directly to the host's PostgreSQL.
- **What stays on the host:** the originals, indexing and metadata, orchestration, and every XMP sidecar write. The host picks worker results up through an outbox.

**Epic:** #435 · **Status:** proposed; nothing is implemented yet.

> **Related, implemented separately:** the [remote GPU runner](../../guides/REMOTE_GPU_RUNNER.md) is a stateless HTTP offload (host sends the input, runner returns the output, host persists). It has no leases, gateway, worker DB role or XMP outbox, and uses its own `gpu_runner` config section so the `remote_worker.*` keys below stay reserved for this design. Its proxies wrap the existing model classes, so a later lease worker can reuse the same server endpoints.

## Decisions already taken

| Question | Decision |
|---|---|
| Where does the worker run? | On another machine on the LAN: trusted network, but not open. |
| What does it download? | **Two modes.** `rendered` means the host serves a JPEG rendition. `original` means the host streams the file bytes and the worker decodes them. The mode can be overridden per phase. |
| Which phases run remotely in the first release? | Every GPU phase: `localization`, `scoring`, `culling` (the embedding extraction), `keywords` and `bird_species`. |
| How do results reach the XMP sidecars? | An automatic outbox drainer on the host (`xmp_sync_outbox` + LISTEN/NOTIFY + polling). |

## Specs

| # | Spec | What it settles |
|---|---|---|
| 01 | [Architecture](01-architecture.md) | Components, trust boundaries, data flow and sequence diagrams |
| 02 | [Worker protocol](02-worker-protocol.md) | Leases and fencing, gateway API, input modes, config sync, versioning |
| 03 | [XMP outbox](03-xmp-outbox.md) | Outbox schema, trigger, drainer, idempotence, failure handling |
| 04 | [Phase decoupling](04-phase-decoupling.md) | How each GPU phase splits compute from persistence and side effects, with file:line citations |
| 05 | [Rollout and testing](05-rollout-and-testing.md) | Milestones, parity tests, security checklist, ops runbook |

## Milestones

| Milestone | Issue | Depends on | Summary |
|---|---|---|---|
| M0 | #436 | — | These specs |
| M1 | #437 | M0 | Host foundations: migration `0036`, worker DB role, gateway, image endpoints, XMP outbox drainer |
| M2 | #438 | M0 | Decoupling: `ImageSource`, compute/persist split, `xmp_sync.emit` (local behaviour unchanged) |
| M3 | #439 | M1, M2 | Worker app: lease loop, fetch cache, fenced persist, `Dockerfile.worker` |
| M4 | #440 | M1, M3 | Host orchestration: `RemotePhaseExecutor`, lease reaper, `auto` mode, status UI |
| M5 | #441 | M4 | Phase rollout with parity tests: scoring → keywords → culling embeddings → localization → bird_species |
| M6 | #442 | M5 | Hardening: TLS, metrics, two-worker load test, runbook |

M1 and M2 can run in parallel. M2 is a refactor with no user-visible change, so it can land first.

## Decision register (open)

| ID | Question | Recommendation | Decide by |
|---|---|---|---|
| D-1 | Should the gateway be its own port and service, or should the webui be exposed on the LAN? | **Its own port and service.** The main API is effectively unauthenticated ([01 §Trust boundaries](01-architecture.md#trust-boundaries)). | M1 |
| D-2 | Should local runs also move to the outbox? | **Not yet.** Keep `xmp_sync.mode=inline` as the default for local work, and revisit after M5. | After M5 |
| D-3 | Where does culling's clustering into stacks run? | **On the host.** Only the embedding extraction moves. | M2 |
| D-4 | What if the two input modes decode RAW differently? | Record the decode route with every result and test parity per mode. No mode is guaranteed to match the other pixel for pixel. | M5 |
| D-5 | Should the drainer protect user-edited XMP? | **Keep today's semantics:** write the current DB state. A guard against user edits is out of scope; see [pipeline spec 04 AC-20](../pipeline-streamlining/04-subject-aware-scoring.md). | M1 |
| D-6 | Should DB access go direct or through the HTTP proxy? | **Direct Postgres with a dedicated role.** Never use `/api/db/query` from the worker. | M1 |

## Related

- [Architecture: DB connector](../../architecture/DB_CONNECTOR.md), whose `ApiConnector` is the existing "remote worker" path. It is not used here; see D-6.
- [Architecture: microservices proposal](../../architecture/microservices_proposal.md): Phase 3 there anticipates a separate scoring service.
- [Pipeline terminology](../../technical/PIPELINE_TERMINOLOGY.md): `phase_code` values.
