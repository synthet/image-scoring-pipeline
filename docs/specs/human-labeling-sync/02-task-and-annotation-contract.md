---
type: Feature Spec
title: "Human labeling sync 02: task and annotation contract"
description: LabelTask and AnnotationEvent v1 as owned by the backend, per-mode answer rules (culling, group culling, binary, pairwise), blindness rules, undo semantics and the changes required from the mobile app and hub.
resource: docs/specs/human-labeling-sync/02-task-and-annotation-contract.md
tags: [specs, labeling, mobile, contract, culling, pairwise]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.1
status: proposed
---

# Human labeling sync 02: task and annotation contract

**Epic:** #453 · **Hub:** [INDEX.md](INDEX.md)

## Baseline

The mobile types in [`src/types/labeling.ts`](https://github.com/synthet/image-scoring-mobile/blob/cursor/mobile-labeler-mvp-fc18/src/types/labeling.ts) (commit `f4feb84`) are the starting point. This spec adopts them as **contract v1**, with the changes listed in [Required changes](#required-changes). The backend publishes the result as JSON Schema under `docs/reference/labeling/` in M4. The mobile repo then regenerates or hand-syncs its types from that schema.

Field names stay camelCase on the wire, matching mobile. Postgres columns are snake_case ([03](03-storage-and-import.md)).

## `LabelTask` (backend → hub → phone)

| Field | Type | Rules |
|---|---|---|
| `id` | string | Backend-generated UUID. Globally unique, never reused. |
| `batchId` | string | `labeling.batches.batch_id` |
| `experimentId` | string | Stable experiment key, for example `culling-415-v1` |
| `schemaVersion` | int | Contract version, `1` |
| `mode` | enum | See [Modes](#modes). The mobile enum also lists `best_of_n`, `rating`, `attribute` and `ranking`; the backend does not emit these in v1. |
| `question` | string | Shown verbatim |
| `items[]` | `{ imageId, assets, metadata? }` | `imageId` = `images.image_uuid` ([01 §Image identity](01-architecture.md#image-identity)). `assets.preview` is a hub URL. `metadata` is **omitted** in blind experiments. |
| `context` | `{ clusterId?, stackId?, selectionReason? }` | **Omitted in blind experiments.** Stack ids and selection reasons reveal strata. The backend keeps them in `labeling.tasks` instead. |
| `config.choices` | string[] | The closed set of valid `answer.choice` values |
| `config.presentation` | object | `show_scores` and `show_metadata` must be `false` for #415 experiments. `allow_zoom` and `allow_undo` must be `true`. |

**Item order is capture order** (`image_exif.date_time_original`, then `images.file_name` as a tie-break at build time). Phones must not reorder items, except pairwise side randomization, which is recorded in the answer.

## `AnnotationEvent` (phone → hub → backend)

| Field | Type | Rules |
|---|---|---|
| `annotationId` | string | UUID generated on the phone. **The idempotency key end to end.** |
| `taskId`, `experimentId`, `schemaVersion` | | Must match the task. A mismatch is quarantined. |
| `answer` | object | Per-mode rules below |
| `client` | `{ deviceId, appVersion }` | Provenance only. **Not** an identity for labels. |
| `interaction` | `{ durationMs, changedAnswer?, zoomUsed?, zoomCount?, undoUsed? }` | `durationMs` feeds `human_labels.unit_status.seconds`. |
| `createdAt` | ISO-8601 | Phone clock. Used to order one labeler's own answers. **Never used as a sync cursor.** |
| `labelerId` | string | **New, hub-stamped** from the token (D-3). Client values are overwritten. |
| `seq` | int | **New, hub-stamped**, monotonic in arrival order. It is the pull cursor ([04](04-sync-and-rollout.md#cursor)). |
| `receivedAt` | ISO-8601 | **New, hub-stamped** |
| `supersedesAnnotationId` | string? | **New, optional**, sent by mobile ([Undo](#undo-and-re-answers)) |

## Modes

### Culling modes

| Mode | Items | Valid answer | Projection into `human_labels` |
|---|---|---|---|
| `culling` (exists) | 1 | `choice ∈ {PICK, KEEP, REJECT}` or `skipped: true` | **None in v1.** A single-frame grade has no group context and no best frame, so it does not satisfy the #415 protocol. It is stored in `labeling.*` only (D-2). |
| `culling_group` (**new, M5**) | 2–12, one #415 unit | `grades: { [imageId]: "PICK" \| "KEEP" \| "REJECT" }` covering **every** item, plus `bestImageId?`; or `skipped: true` with an optional `note` | `labels` gets one row per image, with `grade` 2/1/0 and `is_best`. `unit_status` gets `done` or `skipped`, the note and the seconds. |

`culling_group` validation copies the [#415 save rules](../../planning/human-culling-labels.md#labelling-tool--required-behaviour):
- every frame is graded;
- there is at most one best frame, and it is a `PICK`;
- there is a best frame unless every frame is `REJECT`.

The phone enforces these rules before submitting. The importer enforces them again, and quarantines on failure.

The #415 tool's **flip compare** (the next frame keeps the same zoom and position) is a mobile requirement for `culling_group`. It is listed here so that parity with the desktop tool is tracked, not assumed.

### Binary

`items.length == 1`, and `choice` is in `config.choices`, for example `GOOD` / `BAD`. Stored in `labeling.*` only. Not projected in v1.

### Pairwise

- `items.length == 2`.
- `choice` is in `{LEFT, RIGHT, EQUAL, CANNOT_JUDGE}`.
- `answer.pairwise` is required, as mobile already sends it: `leftImageId`, `rightImageId`, `canonicalImageIds`, `sidesSwapped`, and `winnerImageId` for LEFT/RIGHT.
- The importer stores the **canonical winner**, not the side.
- `EQUAL` and `CANNOT_JUDGE` stay distinct. `CANNOT_JUDGE` is excluded from pairwise-accuracy denominators.
- Not projected into `human_labels` in v1.

## Blindness rules

These rules hold for any experiment tagged `blind: true`, which every #415 experiment is:
- no scores, ranks, filenames, folder or date strings, `context`, or `metadata` in tasks;
- preview JPEGs carry no EXIF;
- asset URLs are content hashes, not ids that could be correlated with the library.

A unit test on the task builder asserts that the serialized task contains no key outside the allow-list ([04 §Tests](04-sync-and-rollout.md#test-matrix)).

## Undo and re-answers

Today mobile undo deletes the local annotation and its outbox row. If the event was **already uploaded**, the hub keeps it, and the re-answer arrives as a second event for the same task. The contract makes that case explicit:

1. Events are never deleted on the hub or the backend.
2. **Current answer** = the latest non-superseded event per (`taskId`, `labelerId`), ordered by `createdAt`, then `seq`.
3. When mobile re-answers a task whose previous event was already synced, it sets `supersedesAnnotationId` to that event.
4. An undo **without** a re-answer, where the user undoes and then leaves, uploads a retraction event: `answer.retracted: true` with `supersedesAnnotationId`. The projection removes that labeler's answer for the task.

## Required changes

| # | Repo | Change | Why |
|---|---|---|---|
| C-1 | mobile hub | Stamp `seq` (monotonic, in arrival order), `receivedAt` and `labelerId` on insert. Pull by `?after_seq=&limit=` and return `next_seq`. | The dev hub filters `created_at > since` on the **phone** clock (`labeling-hub/src/db.ts:204-214`), so late offline uploads with older timestamps are skipped for good, and events with equal timestamps are lost at the boundary. |
| C-2 | mobile hub | Per-labeler mobile tokens that map to `labelerId`; one machine token | Labels are keyed by labeler (#415 multi-labeller, κ overlap) |
| C-3 | mobile hub | `PUT /v1/machine/assets/{sha256}` (idempotent) and `GET /v1/assets/{sha256}` (mobile token) | Previews are served by the hub (D-4) |
| C-4 | mobile hub | Lease stability: re-leasing by the same labeler returns the same assignment. Unleased tasks return to the pool after `leaseExpiresAt`. Batches carry `experimentId`, so assignments can be restricted per labeler. | Offline labeling spans lease windows. The #415 overlap set needs two labelers on the same tasks. |
| C-5 | mobile app | `supersedesAnnotationId`, and retraction events on undo after sync | [Undo](#undo-and-re-answers) |
| C-6 | mobile app | `culling_group` screen: grade every frame, one best frame, flip compare, bulk-grade remaining | D-2, #415 parity (M5) |
| C-7 | mobile app | Honour `presentation.show_scores/show_metadata = false` and never display `imageId` | Blindness |

C-1 to C-4 land before M4 is done. The backend's sync agent is written against the v1 routes in [04](04-sync-and-rollout.md) from the start.
