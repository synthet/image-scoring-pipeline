---
type: Technical Reference
title: Database Schema
description: Routing catalog for the PostgreSQL + pgvector schema — table inventory by area, pgvector notes, and where the authoritative DDL lives.
resource: technical/DB_SCHEMA.md
tags: [database, postgres, pgvector, schema, migrations]
timestamp: 2026-10-29T14:31:18Z
okf_version: 0.2
---

# Database Schema

Migration 0046 adds `localization_policy_approvals`, `localization_policy_events`,
`localization_discovery_state`, `localization_change_journal` and
`localization_selection_lineage`. Approval/control revisions fence publication;
the independent freshness switch defaults off and, when enabled, overrides legacy
reader preferences. See [Localization authority lifecycle](LOCALIZATION_AUTHORITY.md)
for schema ownership, qualification, writer locking, gallery compatibility and rollback.

PostgreSQL + pgvector is the primary database schema for Vexlum Scoring. Older Firebird schema descriptions are historical/migration context only unless current code and docs explicitly say otherwise.

## Canonical Sources

| Source | Role |
|---|---|
| [modules/db_postgres.py](../../modules/db_postgres.py) | Greenfield PostgreSQL DDL used by runtime initialization. |
| [migrations/versions/](../../migrations/versions/) | Alembic revisions for existing databases. |
| [migrations/env.py](../../migrations/env.py) | Alembic connection setup using backend PostgreSQL config. |
| [technical/API_CONTRACT.md](API_CONTRACT.md) | API-level semantics for image identity, filters, and response fields. |
| MCP `get_db_schema` | Live schema inspection when a database is reachable. |

Do not add columns or table names to docs from memory. Confirm in the sources above.

## Primary Tables

The current PostgreSQL initializer creates or maintains these application tables. This is a routing catalog, not a full column reference.

| Area | Tables |
|---|---|
| Localization authority observation | Eight `localization_authority_*` tables (migration 0045): default-off control, immutable scoped policies/evaluations, revision observations, fenced attempts, image reservations, protected proposal lineage and bounded scan faults. These metadata tables confer no production authority. See [LOCALIZATION_AUTHORITY_SHADOW.md](LOCALIZATION_AUTHORITY_SHADOW.md). |
| Library and folders | `folders`, `images`, `file_paths`, `deleted_images`, `pipeline_tool_folder_last_touch` |
| Runs, jobs, and execution trail | `jobs`, `job_phases`, `job_steps`, `job_image_actions`, `pipeline_phases`, `image_phase_status`, `image_incidents` |
| Metadata | `image_exif`, `image_xmp`, image identity fields on `images`. `images.created_at` holds the capture time (indexing writes EXIF DateTimeOriginal; the gallery sorts by it); `images.registered_at` (migration 0041, #584) is when the row was inserted and is never updated; `image_exif.af_metadata` (migration 0044, JSONB) stores normalized autofocus coordinates, mode, crop area, and in-focus lock state from MakerNotes |
| Scoring | composite scores on `images` (`score_general`, `score_technical`, `score_aesthetic`); per-model scores in `image_model_scores` |
| Culling and stacks | `stacks`, `sub_stacks`, `stack_cache`, `cluster_progress`, `culling_sessions`, `culling_picks`, `agent_cull_review_groups`, `agent_cull_recommendations` |
| Keywords | `keywords_dim`, `image_keywords`, legacy keyword text fields where retained for compatibility |
| Embeddings | `embedding_spaces`, `image_embeddings`, `image_embeddings_512`, `image_embeddings_768` (legacy `images.image_embedding` dropped in migration 0024) |
| Localization | `image_localization_runs`, `image_regions` (migration 0034; `image_localization_runs.decode_route` added in 0035 — which decode produced the detector's pixels, e.g. `raw_jpgfromraw` / `raw_preview` / `raw_rawpy` / `direct`). Native current runs can be shadow results; production authority comes from an active selection, not `is_current` alone |
| Localization selections | `image_localization_selections` (migration 0038, #484): the revocable decision that one `image_regions` row is the production answer for an image and detector — `selected_by` (rule version and hash), `evidence` (JSONB), `selected_at` / `revoked_at`. At most one active selection per (image, detector). For a selected image `images.bird_bbox` is a projection written only by `modules/localization_selection.py`; the row keeps `projected_bird_bbox` and the `previous_bird_bbox` it replaced so revocation restores it exactly |
| Localization enablement | `localization_enablement` (migration 0039, #527): one row per `detector_key` with `enabled_at`, the boundary for `localization.new_images_only`. Images with `images.registered_at >= enabled_at` are new and auto-selected; older images are selected only when their source identity changed since their current run, or by an explicit image selection. Not seeded by the migration; `modules/localization_policy.py` inserts it on first enabled use |
| Scene route | `image_scene_labels` (migration 0037, #412): one row per image and `scene_version` (prompt set + backend + prompt hash) with the resolved `top_label`, `top_prob`, every label's `probs` / `cosines` (JSONB) and the localization `rendition_hash`. Written by the scene-route benchmark and, when `scene_route.enabled`, by the `localization` runner |

The opt-in compatibility reader `modules.localization_legacy.read_bird_bbox`
projects the active selection's exact region and its source run's dimensions.
The selected run need not be current, and the selected region need not be rank
zero. Without a selection, an imported legacy payload can be replayed; a native
unselected outcome falls back to `images.bird_bbox`, including negative and
error outcomes. A lookup failure also falls back to the column. With
`localization.read_normalized_first` disabled, the reader only reads the column.
The batch companion `overlay_bird_bboxes` applies these authority rules to copied
API list/detail rows and the visual-evidence region box, with one set-based query
per 500 distinct image IDs. Flag off leaves supplied values unchanged and performs
no normalized lookup. The coordinated gallery reader uses the additive
`image_bird_bbox_compat` view (revision 0043), exposing the active selection
ledger's projection or imported/legacy fallback with the same nullable JSON
shape. Fresh bootstrap creates the same view. Both consumer switches remain
default-off; deploy the view before enabling gallery reads. See the
[compatibility contract](NORMALIZED_BBOX_COMPATIBILITY.md) for authority,
ledger/geometry parity, role checks, migration prerequisites and rollback.
These local reader paths do not complete the Stage 8 compatibility-release gate.

Legacy bbox writes through `db.update_image_bird_bbox`, including the standalone
backfill, use `localization_selection.write_legacy_bird_bbox` (#646). The guard
locks the image row before checking active selection ownership, so a selection
promoted during detection is preserved. A suppressed write returns `False` and
does not invalidate the folder rollup. NULL-only candidate selection is not a
substitute for this transaction guard. The legacy backfill still produces no
normalized run; its retirement or routing remains a separate rollout gate.

## Delegated culling runs (#368, revision 0040)

`jobs.parent_job_id` and `job_phases.delegated_job_id` are nullable, indexed foreign
keys to `jobs.id`. Parent IDs must precede child IDs, preventing cycles. Referenced
jobs cannot be deleted while these links exist. Migration 0040 follows 0039 and
does not infer links from historical queue payloads or rewrite historical statuses.
The same additive DDL lives in `modules/db_schema/core.py` for runtime initialization.

Culling creates the child's complete phase plan and its durable links in the same
transaction that completes the parent's culling stage. Delegated stages mirror the
child's states and timestamps. The parent remains `status='running'`,
`runner_state='waiting_child'`, without a completion timestamp while its child is
queued or running. It occupies no executor slot. Completed child stages remain
completed if a later stage fails; unfinished stages and the parent reflect failure,
cancellation, or interruption, with the child ID in diagnostics.

Startup and idle dispatcher ticks reconcile persisted links. Parent pause/resume
and cancellation control the linked subtree; manual parent-stage changes are
rejected. In-place child retries reopen the parent and preserve completed stages.
Fresh Runs UI retries form independent chains. See
[RUNS_QUEUE_AND_RESTART.md](RUNS_QUEUE_AND_RESTART.md#delegated-culling-runs) for
recovery and deployment instructions. Downgrade refuses unfinished linked chains.

## PostgreSQL / pgvector Notes

- The initializer and migrations create `CREATE EXTENSION IF NOT EXISTS vector`.
- `image_embeddings` stores 1280-dimensional vectors for the default MobileNet space.
- `image_embeddings_512` and `image_embeddings_768` store additional registered spaces.
- HNSW cosine indexes are used for vector search where supported.
- See [EMBEDDINGS.md](../EMBEDDINGS.md) and [technical/EMBEDDINGS.md](EMBEDDINGS.md) for registered space codes, producers, and dimensions.

## Migration Notes

- Alembic revisions live under [migrations/versions/](../../migrations/versions/).
- The initial schema starts at `0001_initial_schema.py`; subsequent revisions add normalized keywords, embeddings, hash/version identity, job execution trails, incidents, GPS/geocode fields, status constraints, model-score rows, pick status, and job status checks.
- Runtime greenfield DDL in [modules/db_postgres.py](../../modules/db_postgres.py) should stay aligned with Alembic-created objects.
- A new table belongs in **three** places: the migration, the runtime DDL, and `POSTGRES_APP_TABLES` in `modules/db_postgres.py` (which drives `truncate_app_tables` between tests).

## Historical Firebird Context

Firebird was the original database and remains documented for migration history and legacy compatibility analysis. Treat Firebird-specific docs as archived or historical unless active support is proven in current code:

- [planning/database/FIREBIRD_POSTGRES_MIGRATION.md](../planning/database/FIREBIRD_POSTGRES_MIGRATION.md)
- [technical/FIREBIRD_WINDOWS_TEMPDIR.md](FIREBIRD_WINDOWS_TEMPDIR.md)
- [archive/plans/database/INDEX.md](../archive/plans/database/INDEX.md)

## Related

- [DATABASE.md](../DATABASE.md)
- [technical/AGENT_COORDINATION.md](AGENT_COORDINATION.md)
- [image-scoring-gallery database design](https://github.com/synthet/image-scoring-gallery/blob/main/docs/architecture/02-database-design.md)
