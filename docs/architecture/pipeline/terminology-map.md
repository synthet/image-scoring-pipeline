---
type: Technical Reference
title: Pipeline Terminology Map
description: One traversal table per phase across every naming system — phase_code, submit token, job_type, runner class, REST endpoints, UI label, DB tables and auto-drive bucket.
resource: architecture/pipeline/terminology-map.md
tags: [pipeline, terminology, naming, api, mapping]
timestamp: 2026-09-01T00:00:00Z
okf_version: 0.1
---

# Pipeline terminology map

The same phase is called seven different things depending on which layer you are standing in.
This page is the single traversal table: pick any name, find all the others.

For the canonical product-facing naming decision, see
[../../technical/PIPELINE_TERMINOLOGY.md](../../technical/PIPELINE_TERMINOLOGY.md). This page is
the wider engineering cross-reference.

## Master table

| `phase_code` | Submit token | `job_type` | Runner class | UI label | Auto-drive bucket |
|---|---|---|---|---|---|
| `indexing` | `indexing` | `indexing` | `IndexingRunner` | **Discovery** | (folded into scoring prefix) |
| `metadata` | `metadata` | `metadata` | `MetadataRunner` | **Inspection** | (folded into scoring prefix) |
| `scoring` | `score` | `scoring` | `ScoringRunner` | **Quality Analysis** | `awaiting_scoring` |
| `culling` | `cluster` | `clustering` / `selection` | `SelectionRunner`, fallback `ClusteringRunner` | **Similarity Clustering** | `awaiting_culling` |
| `keywords` | `tag` | `tagging` | `TaggingRunner` | **Tagging** | `awaiting_keywords` |
| `bird_species` | orchestrated separately | `bird_species` | `BirdSpeciesRunner` | **Bird Species ID** | `awaiting_bird_species` |

Stepper microcopy: **Discovery → Inspection → Quality Analysis → Similarity Clustering → Tagging**.

## REST endpoints per phase

| `phase_code` | Dedicated router endpoints |
|---|---|
| `indexing` | via `/api/pipeline/submit` and `/api/runs/submit` only |
| `metadata` | as above, plus `POST /api/pipeline/phase/backfill-index-meta` |
| `scoring` | `POST /api/scoring/start`, `/stop`, `GET /api/scoring/status`, `POST /api/scoring/single`, `POST /api/scoring/fix-db` |
| `culling` | `POST /api/clustering/start`, `/stop`, `GET /api/clustering/status` |
| `keywords` | `POST /api/tagging/start`, `/stop`, `GET /api/tagging/status`, `POST /api/tagging/single`, `POST /api/tagging/propagate` |
| `bird_species` | `POST /api/bird-species/start`, `/stop`, `GET /api/bird-species/status` |

The legacy single-phase `/start` endpoints for clustering and tagging enqueue their full
prerequisite prefix via `pipeline_prefix_through`, so they cannot run ahead of upstream work.

## Primary tables written

| `phase_code` | Primary work product |
|---|---|
| `indexing` | `images` (`file_path`, `file_name`, `image_hash`, `hash_version`, `folder_id`, `metadata`), `folders`, `file_paths` |
| `metadata` | `image_exif`, `image_xmp`, `images` (`image_uuid`, `thumbnail_path`, `thumbnail_path_win`) |
| `scoring` | `image_model_scores`, `images` (`score_general`, `score_technical`, `score_aesthetic`, `rating`, `label`, `model_version`), `image_technical_failures` |
| `culling` | `stacks`, `sub_stacks`, `images` (`stack_id`, `sub_stack_id`, `burst_uuid`, `cull_decision`, `cull_policy_version`, `pick_status`), `image_embeddings*`, `cluster_progress` |
| `keywords` | `keywords_dim`, `image_keywords`, `images` (`keywords`, `title`, `description`), `image_xmp` accessibility, `image_embeddings_512/768` |
| `bird_species` | `image_keywords` (`species:*`), `images.bird_bbox` |

Every phase additionally writes `jobs`, `job_phases`, `image_phase_status`, `job_image_actions`
and `auditlog`.

## Alias resolution

Three modules each carry their own alias map. They agree on the common cases but differ in reach.

**`modules/phases.py:240-244`** — canonical, used by `normalize_phase_codes`:

| Alias | Resolves to |
|---|---|
| `score` | `scoring` |
| `tag` | `keywords` |
| `cluster` | `culling` |

**`modules/run_phase_planner.py:24-31`** — the widest set:

| Alias | Resolves to |
|---|---|
| `clustering`, `selection` | `culling` |
| `tagging`, `tag` | `keywords` |
| `score` | `scoring` |
| `bird-species` | `bird_species` |

**`modules/job_dispatcher.py:531-538`** — phase to queue key:

| Alias | Queue key |
|---|---|
| `score` | `scoring` |
| `tagging`, `tag` | `keywords` |
| `selection` | `culling` |
| `cluster` | `clustering` |

**`modules/db_legacy.py:6519-6532`** — `PHASE_CODE_TO_RUNNER_KEY`, for busy checks:

| Phase code | Runner key |
|---|---|
| `indexing` | `indexing` |
| `metadata` | `metadata` |
| `scoring`, `score` | `scoring` |
| `keywords`, `tagging`, `tag` | `tagging` |
| `culling`, `selection` | `selection` |
| `clustering`, `cluster` | `clustering` |
| `bird_species` | `bird_species` |

Note `culling` and `clustering` resolve to **different** runner keys here, because
`SelectionRunner` and `ClusteringRunner` are distinct objects that can be busy independently.

## Submit field naming

The canonical request field is **`stage_codes`**. `operations` is a *validation alias* retained
for older clients (`modules/api_models.py:604`, `AliasChoices("stage_codes", "operations")`).
Prefer `stage_codes` in new code and documentation.

Accepted tokens: `indexing`, `metadata`, `score`, `tag`, `cluster`
(`modules/api/routers/pipeline_submit.py:98`). Constraints:

- Single-file submissions support only `score` and `tag`.
- `cluster` requires a folder path.

## Status vocabulary cross-reference

| Concept | Image (`image_phase_status`) | Run stage (`job_phases`) | Folder rollup |
|---|---|---|---|
| Not begun | `not_started` | `pending` | `not_started` |
| Waiting | `queued` | `queued` | `queued` |
| Active | `running` | `running` | `running` |
| Held | `paused` | `paused` | `paused` |
| Stopping | `cancel_requested` | `cancel_requested` | `cancel_requested` |
| Restarting | `restarting` | `restarting` | `restarting` |
| **Succeeded** | **`done`** | **`completed`** | **`done`** |
| Deliberately not done | `skipped` | `skipped` | `skipped` |
| Errored | `failed` | `failed` | `failed` |
| Abandoned mid-flight | — | `interrupted` | — |
| Stopped by user | — | `canceled` | — |
| Mixed | — | — | `partial` |

## Runs vs jobs

- **Database:** batch rows live in `jobs`; stage rows in `job_phases`.
- **React SPA:** each `jobs` row is a **Run** (`frontend/src/types/api.ts`, type `Run`).
- **Electron gallery:** user-facing copy says *run* ("Recent runs", "Queue run") while still
  passing `job_id` to the API.
- **MCP:** still `job_id` and `get_recent_jobs`.

## Sub-step names

`frontend/src/types/api.ts` `STEP_DISPLAY`:

| `step_code` | Display |
|---|---|
| `musiq` | Multi-Scale Quality |
| `liqe` | Learned Quality |
| `topiq` | Top-Down Quality |
| `qalign` | Alignment Quality |
| `blip` | BLIP Captioning |
| `clip` | CLIP Tagging |

> Two caveats. These map to the unpopulated `job_steps` table, so nothing currently emits them.
> And `qalign` names a model **this backend does not implement** — see
> [phases/scoring.md](phases/scoring.md). The genuinely active scorers include `arniqa`, which
> has no entry here.

## Known gaps

- Four separate alias maps exist, in `phases.py`, `run_phase_planner.py`, `job_dispatcher.py` and
  `db_legacy.py`. They are consistent today but nothing enforces that.
- `PIPELINE_TERMINOLOGY.md` labels the submit column `operations`; the canonical field is
  `stage_codes`.
- `STEP_DISPLAY` lists a model that does not exist and omits one that does.

## Related

- [../../technical/PIPELINE_TERMINOLOGY.md](../../technical/PIPELINE_TERMINOLOGY.md) — product naming authority
- [phase-graph.md](phase-graph.md) — the phases themselves
- [persistence.md](persistence.md) — the tables named above
- [run-lifecycle.md](run-lifecycle.md) — the endpoints in context
