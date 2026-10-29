---
type: Technical Reference
title: Localization authority shadow execution
description: Default-off observational localization authority metadata, reservations, fenced work and operator commands.
resource: technical/LOCALIZATION_AUTHORITY_SHADOW.md
tags: [localization, postgres, shadow, operations]
timestamp: 2026-10-29T14:31:18Z
okf_version: 0.2
---
# Localization authority shadow execution

The authority worker evaluates existing localization artifacts and persists proposed
actions. It starts with `JobDispatcher` on a separate CPU thread, so busy ingestion
or GPU runners do not stop observation. Its durable mode defaults to `off`.

`shadow` writes only the metadata tables below. It cannot publish selections,
`bird_bbox`, keywords, embeddings, eligibility changes or GPU work. `active` is
rejected by both the database constraint and maintenance CLI. Policy registration
is an observation scope, not approval or evidence that #694 passes qualification.

## Persistence and identities

[Migration 0045](../../migrations/versions/0045_localization_authority.py) and
[bootstrap DDL](../../modules/db_schema/authority.py) install eight additive tables:

| Table | Purpose |
|---|---|
| `localization_authority_control` | Default-off mode, control revision, durable scan cursor and finite sweep watermark, verified reservation inventory hash. |
| `localization_authority_policies` | Immutable rule identity and exact model/config/rendition observation scope; approval revision remains zero. |
| `localization_authority_evaluations` | Immutable positive and negative results, unique by artifact fingerprint and observation-policy hash. |
| `localization_authority_observations` | Separate authority, discovery, ownership, source-observation and reservation revisions. These record observations without granting eligibility or adopting outputs. |
| `localization_authority_attempts` | Evaluation plus revision-context identity, lease, fencing token, retries, disposition and proposed actions. |
| `localization_authority_reservations` | Image-level frozen-cohort reservations retaining original run/region identities and inventory hash. No release operation is implemented. |
| `localization_authority_lineage` | Proposed input/action lineage, always marked `outputs_protected`; it is not ownership of production outputs. |
| `localization_authority_scan_faults` | Durable per-input fault budget and 60/300-second retry schedule; the third failure exhausts that input. |

The observation-policy hash includes the pinned R2 rule hash and explicit producer
scope. It differs from the registered #694 protocol hash. Evaluation stores the
original population snapshot once; mutable context changes reopen application
attempts using the cached evaluation. A new artifact or policy gets a new result.
This deliberately does not broaden R2 to images outside its original population.

Worker claims increment a fencing token and lease work for 60 seconds, with a
20-second heartbeat. Renewal and completion require the current token and an
unexpired lease. Completed proposals/abstentions do not reopen on lease expiry.
Unfinished claims have at most three attempts. Publication checks the current
mode revision, observation revision, producer scope and captured inputs again.

Publication lock order is control, policy, image, observation/work/lineage.
Claim transactions finish before publication begins. Mode changes take an
exclusive control lock; metadata publication takes a shared lock, preventing a
mode change from interleaving with its publication transaction.

## Scans, source evidence and protected state

Default polling is five seconds with batches capped at 100. Each sweep captures a
finite run-ID watermark; new ingestion cannot indefinitely prevent revisiting old
images. Cursor advancement follows durable observation/fault recording. Restart
replays unfinished batches safely through database uniqueness constraints.

Source checks use the existing `rendition.source_identity` contract outside database
transactions. This samples size, second-resolution mtime and the first 64 KiB; it
is not a full-content guarantee. Unreadable or changed sources cannot propose a
fresh selection. No RAW decode or inference is performed.

The original receipt and all four frozen input hashes must verify before reservation
import. All 30,046 cohort image IDs are reserved, not only the 390 validation IDs.
Reservations survive new runs, repairs, source changes and removal of the image row.
An absent/unverified inventory is reported as an application blocker. Import never
releases an existing reservation. Current code performs no automatic application.

Legacy discovery and species outputs remain protected. Keyword/source observations
are not a new provenance grant. Atomic writer invalidation, curated-edit ownership,
reader freshness, active authority and species convergence remain later lifecycle
work tracked by the [localization rollout](../architecture/pipeline/localization-rollout.md).

## Operator commands

Run from the backend root inside the documented GPU-shell environment. Commands
that mutate metadata require the exact connected database name. These are examples;
the implementation task did not enable observation on the production database.

```bash
python -m scripts.maintenance.localization_authority status
python -m scripts.maintenance.localization_authority verify-inventory --root .agent/scratch/promotion-694
python -m scripts.maintenance.localization_authority --expect-database image_scoring_test register-policy --rule tests/fixtures/localization/rule-frozen-20261026.json --detector-version MODEL_VERSION --detector-config-hash CONFIG_HASH --rendition-version RENDITION_VERSION
python -m scripts.maintenance.localization_authority --expect-database image_scoring_test import-reservations --root .agent/scratch/promotion-694
python -m scripts.maintenance.localization_authority --expect-database image_scoring_test set-mode shadow
python -m scripts.maintenance.localization_authority --expect-database image_scoring_test run-once
python -m scripts.maintenance.localization_authority --expect-database image_scoring_test set-mode off
```

The CLI exposes no approval, reservation release or active-mode operation. Turning
observation off preserves all existing production selections and outputs.

## Diagnostics and verification

`GET /api/runs/drive/status` adds optional `localization_authority` diagnostics,
cached by the worker: availability/running state, mode/revision, scan position,
backlog age, decision reasons, attempt dispositions, reservation conflicts,
fenced publication rejections, scan faults and proposed species actions. Unavailable
metadata reports its state without changing existing drive/lane response fields.

The PostgreSQL suite uses `image_scoring_test` on the isolated `db-e2e` service.
It covers an actual forward migration in a rollback-only schema, bootstrap parity,
immutability, competing observers/claims, expired tokens, revision round trips,
concurrent mode changes, restart recovery, finite sweeps, bounded faults and unchanged
production image/selection/keyword/embedding/phase/job tables. Unit tests cover the
frozen rule, inventory tampering, CLI database guards and dispatcher ownership.

Migration 0045 creates metadata and indexes without rewriting existing image tables
or backfilling output ownership. Test fixtures include all eight tables and restore
the default-off singleton. Apply to production only through the normal reviewed
migration procedure. Rollback of observation is `set-mode off`; dropping metadata
requires a separate maintenance decision and loses observation history.
