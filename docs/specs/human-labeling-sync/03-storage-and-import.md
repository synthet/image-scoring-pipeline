---
type: Feature Spec
title: "Human labeling sync 03: storage and import"
description: Proposed Postgres `labeling` schema, bringing the hand-created `human_labels` schema under Alembic without data loss, append-only annotation import with quarantine, and the projection into human_labels for #415 experiments.
resource: docs/specs/human-labeling-sync/03-storage-and-import.md
tags: [specs, labeling, postgres, alembic, human-labels, import]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.1
status: proposed
---

# Human labeling sync 03: storage and import

**Epic:** #454 · **Hub:** [INDEX.md](INDEX.md)

All DDL below is **proposed**. Nothing exists until M1 lands:
- an Alembic migration at the next free revision when M1 starts. Master already has `0036_region_keypoints`, and [remote GPU worker M1](../remote-gpu-worker/05-rollout-and-testing.md#milestones) also plans a migration, so check `migrations/versions/` and `alembic heads` first;
- the same DDL mirrored in `modules/db_postgres.py`;
- documented in [DB_SCHEMA.md](../../technical/DB_SCHEMA.md).

## Schemas

The tables sit in **dedicated schemas**, not `public`, for the same reason #415 gives: dropping research or broker data must never delete labels.

| Schema | Owner | Holds |
|---|---|---|
| `human_labels` | #415, adopted by Alembic in M1 | The evaluation label set: units, per-image labels, per-unit status |
| `labeling` | this spec | Experiments, batches, tasks, raw events, cursors, rejects, preview assets |

## Adopting `human_labels` (M1)

The schema already exists in the operator's database, holding real labels, and was created by hand. The migration must:

1. `CREATE SCHEMA IF NOT EXISTS human_labels` and `CREATE TABLE IF NOT EXISTS` for `units`, `labels` and `unit_status`, with exactly the columns documented in [human-culling-labels.md §Storage](../../planning/human-culling-labels.md#storage).
2. **Inspect first.** Before creating anything, compare the live columns with the expected ones through `information_schema.columns`. On any mismatch, **abort the migration with a clear message.** Never alter or drop a live labels table automatically.
3. Add only keys that are missing and safe: the primary keys (`labels (unit_id, image_id, labeler)`, `unit_status (unit_id, labeler)`) if absent, created `IF NOT EXISTS`.
4. Add one nullable provenance column to `labels` and to `unit_status`: `source_event_id UUID NULL`. Desktop-tool rows keep NULL.
5. `downgrade()` drops only what this migration added (the provenance columns), never the tables.

**Acceptance:** run the migration against a restored `pg_dump -n human_labels` snapshot. Row counts and a checksum of `labels` must be identical before and after.

## `labeling` tables

| Table | Key columns | Notes |
|---|---|---|
| `experiments` | `experiment_id TEXT PK`, `mode`, `question`, `choices TEXT[]`, `schema_version`, `blind BOOL`, `projects_to TEXT NULL` (`human_labels` or NULL), `definition JSONB`, `created_at` | One row per versioned definition. Changing the question or choices means a **new** `experiment_id`. |
| `batches` | `batch_id UUID PK`, `experiment_id FK`, `state` (`draft` / `pushed` / `closed`), `pushed_at`, `task_count` | |
| `tasks` | `task_id UUID PK`, `batch_id FK`, `position`, `unit_id INT NULL` (→ `human_labels.units`), `image_ids INT[]`, `payload JSONB` (exactly what was pushed), `context JSONB` (private: strata, stack, reason) | `payload` is the audit record of what the labeler saw. |
| `preview_assets` | `sha256 CHAR(64) PK`, `image_id INT`, `rendition_key TEXT`, `bytes INT`, `uploaded_at NULL` | Dedup and re-push. The JPEG itself lives in the backend's preview cache ([04](04-sync-and-rollout.md#preview-pipeline)). |
| `annotation_events` | `annotation_id UUID PK`, `hub_seq BIGINT UNIQUE`, `task_id FK`, `experiment_id`, `labeler_id TEXT`, `created_at TIMESTAMPTZ`, `received_at TIMESTAMPTZ`, `imported_at`, `supersedes UUID NULL`, `payload JSONB`, `payload_sha256` | **Append-only.** No `UPDATE` or `DELETE` in application code. |
| `annotation_rejects` | `annotation_id`, `hub_seq`, `reason`, `detail`, `payload JSONB`, `seen_at` | Quarantine. Reasons: `schema_version`, `unknown_task`, `image_missing`, `invalid_choice`, `invalid_group`, `payload_conflict` |
| `sync_cursors` | `hub_url TEXT PK`, `last_seq BIGINT`, `updated_at` | One per hub |

The current-answer view is `labeling.current_answers`: the latest non-superseded, non-retracted event per (`task_id`, `labeler_id`), per [02 §Undo](02-task-and-annotation-contract.md#undo-and-re-answers).

## Import

`modules/labeling/importer.py`, driven by `labeling_sync.py pull-annotations`, handles each page of events in **one transaction**:

1. **Validate** each event against [02](02-task-and-annotation-contract.md), plus the task's stored `payload`: the image ids belong to the task and the choice is in `choices`. Failures go to `annotation_rejects`.
2. **Insert** valid events with `INSERT … ON CONFLICT (annotation_id) DO NOTHING`. If the id already exists with a **different** `payload_sha256`, record `payload_conflict` in rejects and keep the first event.
3. **Project** the affected (task, labeler) pairs where `experiments.projects_to = 'human_labels'` (see below).
4. **Advance** `sync_cursors.last_seq` to the page's `next_seq`.

The page commits or rolls back as a whole, so re-running a pull is always safe.

### Projection into `human_labels`

This applies to `culling_group` tasks with a `unit_id`. `culling` single-frame tasks are never projected (D-2).

| Current answer | `human_labels.labels` | `human_labels.unit_status` |
|---|---|---|
| Graded unit | Upsert one row per image: `grade` (PICK=2, KEEP=1, REJECT=0), `is_best`, `labeler`, `updated_at = created_at`, `source_event_id` | `status='done'`, `seconds = durationMs/1000`, `source_event_id` |
| `skipped` | Delete this labeler's rows for the unit **only where `source_event_id` is not NULL** | `status='skipped'`, `note` |
| Retracted | Delete this labeler's mobile-sourced rows for the unit | Delete this labeler's mobile-sourced status row |

**Labeler namespace:** `labeler = 'mobile:' || labeler_id`. Mobile labels therefore never overwrite rows written by the desktop tool for the same person. The evaluation can merge the two sources explicitly, or keep them apart to measure within-person consistency across channels.

**Never touched:** `images.pick_status`, `images.cull_decision`, `culling_picks`, XMP. Human labels are evaluation data only ([01 §Non-goals](01-architecture.md#non-goals)).

## Label audit integration

`modules/score_analytics/labels.py` currently recognizes only `culling_picks` with `auto_suggested = 0` as independent labels (`labels.py:5`, `:80`). In M3, add `human_labels.labels` as a third source, preferred and separately reported. This resolves the open "Integration (proposed)" question in [human-culling-labels.md §Storage](../../planning/human-culling-labels.md#storage) in favour of reading `human_labels` directly, which keeps groups and weights.
