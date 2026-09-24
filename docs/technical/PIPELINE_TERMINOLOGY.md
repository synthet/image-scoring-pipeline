---
type: Technical Reference
title: Pipeline Terminology
description: Canonical mapping between user-facing stage names, DB phase_code values, submit tokens, and REST/runner identifiers.
resource: technical/PIPELINE_TERMINOLOGY.md
tags: [pipeline, terminology, phases, naming]
timestamp: 2026-09-01T00:00:00Z
okf_version: 0.1
---

# Pipeline terminology (Gradio, Vite UI, API, DB)

User-visible names are aligned across the **Gradio Pipeline** tab (`/app`), the **React SPA** (`/ui/`, source under `frontend/`), and the **Electron gallery** ([image-scoring-gallery](https://github.com/synthet/image-scoring-gallery)). Internal identifiers (`phase_code`, REST paths, `job_type`) stay stable for compatibility; this page maps them to product language.

## Canonical stage display names

Source of truth in this repo: **`frontend/src/types/api.ts`** — `STAGE_DISPLAY` (and `STEP_DISPLAY` for sub-steps such as MUSIQ, LIQE).

| `phase_code` (DB / `job_phases`) | Submit `stage_codes` token | User-facing name | Notes |
|----------------------------------|-----------------------------------------------|------------------|--------|
| `indexing` | `indexing` | **Discovery** | Scan and register files |
| `metadata` | `metadata` | **Inspection** | EXIF/XMP, thumbnails |
| `localization` | `localization` | *(not user-facing yet)* | Shadow-only subject regions; **hidden and rejected while `localization.enabled` is false** (see below) |
| `scoring` | `score` | **Quality Analysis** | ML quality scores |
| `culling` | `cluster` | **Similarity Clustering** | Stacks / similarity grouping |
| `keywords` | `tag` | **Tagging** | Keywords and captions |
| `bird_species` | (orchestrated separately) | **Bird Species ID** | Optional phase after Tagging |

**Submit field name:** the canonical request field is **`stage_codes`**. `operations` is retained as a
Pydantic `validation_alias` for older clients (`modules/api_models.py:604`,
`AliasChoices("stage_codes", "operations")`) — prefer `stage_codes` in new code. Accepted tokens are
validated at `modules/api/routers/pipeline_submit.py:98`; single-file submissions support only `score`
and `tag`, and `cluster` requires a folder path.

**Config-gated phases.** `localization` (#387, rollout stage 4) is registered in the backend
(`PhaseCode`, `PHASE_PREREQUISITES`, executor, `pipeline_phases` row) but gated by
`localization.enabled` (default `false`, `PHASE_ENABLED_CONFIG_KEYS` in `modules/phases.py`).
While off it is omitted from public phase lists (scope preview, folder phase summary via
`pipeline_phases.enabled`, the valid-token list in submit errors) and from the OpenAPI
descriptions; `/api/runs/submit`, `/api/pipeline/submit` and the job dispatcher reject it with an
error naming the key; auto-drive never targets it. The gallery and SPA stage lists are updated in
the slice that enables it.

**Phase dependencies are a DAG, not the linear order above.** `culling` and `keywords` are siblings
that both depend only on `scoring`. See
[../architecture/pipeline/phase-graph.md](../architecture/pipeline/phase-graph.md).

Gradio copies these titles on the Pipeline cards (e.g. “Quality Analysis”, “Similarity Clustering”, “Tagging”) and in the stepper microcopy: **Discovery → Inspection → Quality Analysis → Similarity Clustering → Tagging**.

## REST and runner names (unchanged)

These are **not** the same as stage titles; UIs should map them when showing notifications or progress:

| Area | Typical identifier | Maps to stage / action |
|------|----------------------|-------------------------|
| `/api/scoring/*` | `job_type` `scoring` | Quality Analysis |
| `/api/tagging/*` | `job_type` `tagging` | Tagging (`keywords` phase) |
| `/api/clustering/*` | `job_type` `clustering` | Similarity Clustering (`culling` phase) |

## Indexing fulfillment vs folder rollup

- **Folder rollup** (`get_folder_phase_summary`, cached in `folders.phase_agg_json`) aggregates per-image `image_phase_status` under a folder path and its descendants. The Scope Navigator dots derive from this cache (may lag until aggregates refresh).
- **Fulfillment stats** (`get_folder_fulfillment_stats_for_path`) use the **same subtree image set** and report concrete counts and percentages: scores, thumbnails, keywords, and **`indexing_pct`** (share of images whose indexing IPS row is `done` or `skipped`).
- **Orchestrator healing:** when the rollup says a phase is `done` but fulfillment is below a high threshold (99.9% for indexing, scoring, and metadata thumbnails), `PipelineOrchestrator` may still schedule that phase so catch-up runs can repair gaps.

## Runs vs jobs

- **Database:** batch rows live in the `jobs` table; phase rows in `job_phases`.
- **React Runs UI:** treats each row as a **Run** (see `frontend/src/types/api.ts` `Run`).
- **Electron:** user-facing copy prefers **run** (e.g. “Recent runs”, “Queue run”) while still using `job_id` from the API.

## Related docs

- [ELECTRON_SYNC_IMPORT_AND_PHASES.md](ELECTRON_SYNC_IMPORT_AND_PHASES.md) — After **image-scoring-gallery** “Sync from device”: IPS rows, `jobs`, and common confusion between **`indexing`** (Discovery) vs **Inspection** / downstream phases
- [RUN_OPTIONS_MODE_MATRIX.md](RUN_OPTIONS_MODE_MATRIX.md) — New Run execution options vs `run_mode` / dispatcher (supplements stage naming above)
- [../architecture/pipeline/INDEX.md](../architecture/pipeline/INDEX.md) — comprehensive pipeline set: phase graph, status machines, preconditions, control plane, persistence
- [../architecture/pipeline-architecture.md](../architecture/pipeline-architecture.md) — short architecture summary
- [GRADIO_UI_UX_SPEC_FOR_ELECTRON_MIGRATION.md](GRADIO_UI_UX_SPEC_FOR_ELECTRON_MIGRATION.md) — Gradio UX mirror for Electron
- [API_CONTRACT.md](API_CONTRACT.md) — REST overview

**Sibling repo:** [image-scoring-gallery `docs/technical/PIPELINE_TERMINOLOGY.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/technical/PIPELINE_TERMINOLOGY.md) — renderer constants and file pointers.
