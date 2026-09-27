---
type: Feature Spec
title: "Human labeling sync 04: sync agent and rollout"
description: The labeling_sync CLI (push-batch, pull-annotations, status), hub v1 machine routes, sequence cursor, blind preview pipeline, proposed config and secrets, milestones with exit criteria, test matrix and operator runbook.
resource: docs/specs/human-labeling-sync/04-sync-and-rollout.md
tags: [specs, labeling, sync, previews, rollout, testing, runbook]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.1
status: proposed
---

# Human labeling sync 04: sync agent and rollout

**Epic:** #454 · **Hub:** [INDEX.md](INDEX.md)

## Sync agent CLI

`scripts/labeling_sync.py` (D-6) runs where the app scripts run, in `image-scoring-gpu-shell`. It uses the `modules.labeling` package and the normal DB connection.

| Command | Does |
|---|---|
| `push-batch --experiment <id> [--limit N] [--labeler <id>] [--dry-run]` | Builds a batch (draft), renders missing previews, uploads missing assets, pushes the manifest, and marks the batch `pushed`. `--dry-run` prints the task count and a redacted sample task only. |
| `push-batch --resume <batch_id>` | Re-pushes an existing batch, for example after a hub wipe. Idempotent. |
| `pull-annotations [--max-pages N]` | Pages through `after_seq` until it is caught up, and imports ([03 §Import](03-storage-and-import.md#import)). |
| `status` | Per experiment: tasks pushed, answered, per-labeler progress, reject counts by reason, cursor lag. Read-only. |

Exit codes: `0` on success, `2` when events were quarantined (the run still succeeded), `1` on failure. That makes a scheduler alert on quarantine easy.

## Hub v1 machine routes

These routes are consumed by the backend and implemented in the mobile repo's hub, per [02 §Required changes](02-task-and-annotation-contract.md#required-changes).

| Method | Path | Body / query | Response |
|---|---|---|---|
| `GET` | `/health` | — | `{ ok, version }` |
| `HEAD` | `/v1/machine/assets/{sha256}` | — | `200` if present, `404` if not |
| `PUT` | `/v1/machine/assets/{sha256}` | `image/jpeg` bytes | `201` or `200`. The hub verifies the SHA-256 and rejects a mismatch with `400`. |
| `POST` | `/v1/machine/batches` | `LabelBatch` whose `items[].assets.preview` is `hub://assets/{sha256}` | `{ batchId, taskCount }`. An upsert by `batchId`. The hub rewrites `hub://` to its public asset URL. |
| `GET` | `/v1/machine/annotations?after_seq=&limit=` | `limit` ≤ 500 | `{ annotations: AnnotationEvent[], next_seq }`, ordered by `seq` |

The dev hub today has `POST /v1/machine/batches` and `GET /v1/machine/annotations?since=` only.

### Cursor

The cursor is the **hub-assigned `seq`**, never `createdAt`.
- Phones upload offline work hours or days late, with old `createdAt` values.
- A timestamp cursor, as the dev hub uses today with `created_at > since`, permanently skips those events. It also drops events that share the boundary timestamp.
- `seq` is assigned on arrival, strictly increasing, so `after_seq` is gap-free.

## Preview pipeline

`modules/labeling/previews.py`:

1. **Source pixels:** the decode-once rendition when it is available ([pipeline spec 01](../pipeline-streamlining/01-rendition.md), `modules/rendition.py`). Until then, the same orientation-baked decode path used for thumbnails. RAW/NEF must go through the existing decode route, and the regression-test rule for RAW/EXIF changes applies.
2. **Resize** so the long edge is 1600 px (proposed default) and bake the orientation.
3. **Encode** as a JPEG at a fixed quality **with no metadata**: no EXIF, XMP, ICC beyond sRGB, or GPS. This makes encoding deterministic, so the SHA-256 is stable. It follows the same properties as `modules/crop_cache.py`: atomic write and content-addressed storage.
4. **Store** under a backend preview cache directory keyed by SHA-256, and index it in `labeling.preview_assets`.

Tests assert:
- no EXIF or GPS in the output;
- the orientation is correct on the rotated NEF/JPEG fixtures;
- re-encoding is byte-identical.

## Config and secrets (proposed)

These keys are **proposed**, not existing; per the development guidelines they are not invented until M4 adds them to `config.example.json` and [CONFIG.md](../../technical/CONFIG.md).

| Key | Where | Purpose |
|---|---|---|
| `labeling.hub_url` | `config.json` | Hub base URL (HTTPS in production) |
| `labeling.preview_long_edge` | `config.json` | Default `1600` |
| `labeling.preview_cache_dir` | `config.json` | Content-addressed JPEG cache |
| `labeling.pull_page_size` | `config.json` | Default `500` |
| `labeling_hub_machine_token` | **`secrets.json`** | Machine bearer token. Never in `config.json`, logs or `status` output. |

## Milestones

| M | Delivers | Exit criteria |
|---|---|---|
| M1 | Alembic migration (the `labeling` schema + `human_labels` adoption), mirrored in `modules/db_postgres.py`; `modules/labeling/repository.py`; [DB_SCHEMA.md](../../technical/DB_SCHEMA.md) updated; `image_uuid` backfill for sampled images | The migration passes on an empty DB and on a restored `human_labels` snapshot, with an identical checksum. Postgres tests for append-only inserts and `current_answers`. |
| M2 | `experiments` (definitions in code, synced to `labeling.experiments`), `task_builder` (#415 units source: `sample_order`, skip units done by the labeler), `previews` | Blindness allow-list test. Preview tests. `push-batch --dry-run` against a fixture DB. |
| M3 | `importer` + projection + `annotation_rejects`; the label audit reads `human_labels` | Postgres tests: replaying the same page is a no-op; out-of-order `createdAt` imports; supersede/retract; a `payload_conflict` is quarantined; desktop-tool rows are never modified. |
| M4 | `scripts/labeling_sync.py`; hub v1 (C-1 to C-4) and mobile C-5 and C-7 landed in image-scoring-mobile; JSON Schema under `docs/reference/labeling/`; config keys documented | E2E against a real hub container: push → a simulated phone labels (including a late offline upload) → pull, with every event imported exactly once. |
| M5 | Mobile `culling_group` (C-6) and a `culling-415-v1` experiment with `projects_to = human_labels` | 10 real units labelled on a phone appear in `human_labels` under `mobile:<id>`. Validation parity with the desktop tool. |
| M6 | TLS-only hub, per-labeler token rotation, preview retention (delete hub assets for closed batches), runbook verified | A drill: wipe the hub, then `push-batch --resume` restores it, with no event lost that had already been pulled. |

## Test matrix

The markers follow `pytest.ini` and the E2E vocabulary in `AGENTS.md`.

| Layer | Suite | Covers |
|---|---|---|
| Unit (fast subset) | `tests/test_labeling_*.py` | Task serialization allow-list (blindness), choice and group validation, grade mapping, current-answer resolution (supersede, retract, tie on `createdAt` → `seq`), cursor paging, a fake hub client, token redaction in logs and `status` |
| Unit | `tests/test_labeling_previews.py` | Metadata stripped, orientation, deterministic bytes |
| Postgres integration (`-m postgres`) | `tests/integration/test_labeling_import_e2e.py` | Migration on a snapshot, idempotent import, rejects, projection, desktop rows untouched |
| Cross-repo E2E | M4 exit test | Real hub container + scripted phone client |

## Runbook (draft)

1. **First run:** set `labeling.hub_url`, put the machine token in `secrets.json`, run `alembic upgrade head`, then `scripts/doctor.py`.
2. **Label a batch:** run `push-batch --experiment culling-415-v1 --limit 30 --labeler <id>` and label on the phone.
3. **Import:** run `pull-annotations`, then `status`. Investigate any non-zero reject count before the next push.
4. **Snapshot** after each session, as #415 already does: `pg_dump -n human_labels -n labeling`.
5. **Hub lost:** `push-batch --resume <batch_id>` for open batches. Ask labelers to keep the app open until their outbox is empty.
