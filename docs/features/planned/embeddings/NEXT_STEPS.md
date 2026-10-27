---
type: Implementation Plan
title: Embedding features next steps
description: Delivered multi-space endpoints and remaining persistence, job and UI proposals.
resource: features/planned/embeddings/NEXT_STEPS.md
tags: [docs, planning, next-steps]
timestamp: 2026-10-13T00:58:42Z
okf_version: 0.2
---

# Embedding Features: Next Steps Roadmap

This document summarizes the current implementation status and the **true remaining gaps** for the 8 proposed embedding applications.

**Code review refreshed 2026-10-12:** multi-space/PCA and the embedding-space
registry routes are implemented in `modules/api/routers/embedding.py`.
Persistent projection storage, HDBSCAN and `modules/projection_runner.py` remain
proposals in this checkout. The queue is the GitHub Project board, not a new
local task list. [The current handoff](../../../../NEXT_STEPS.md) covers separate
localization operational blockers; its agent species/box labels are not culling
ground truth and do not approve embedding-space or scoring-default changes.

## Status Overview

| App | Feature | Status | Implementation Notes |
|:---|:---|:---|:---|
| 01 | Diversity Selection | **Implemented** | `diversity.py` (MMR) integrated in `selection.py`. |
| 02 | Near-Duplicate Detection | **Implemented** | `similar_search.py` (`find_near_duplicates`). |
| 03 | Tag Propagation | **Implemented** | `tagging.py` (`propagate_tags`). |
| 04 | Outlier Detection | **Implemented** | `similar_search.py` (`find_outliers`). |
| 05 | 2D Embedding Map | **Backend v1 + Phase 1 multi-space shipped / Persistent + UI pending** | Projection service in `modules/projections.py`; `GET /api/embedding_map` accepts `space_code` and `pca_dim`. Multi-space reads via `modules/projections_db.get_embeddings_with_metadata_for_space`. Coverage in `tests/test_api_embedding_map.py`. Persistent projections table + HDBSCAN (phase 2) and React atlas UI (phase 3) remain — see [EMBEDDING_APP_05_2D_EMBEDDING_MAP.md](EMBEDDING_APP_05_2D_EMBEDDING_MAP.md) §Roadmap. |
| 06 | Smart Stack Representative | **Implemented** | Centroid representative selection is implemented in `modules/clustering.py` (`_select_best_image`, `stack_representative_strategy`). |
| 07 | "More Like This" UI | **Partial** | Search logic and REST API exist; UI wiring is still needed. |
| 08 | Gradio Integration | **Partial** | Backend APIs exist, but bidirectional control and orchestration work remain. |

---

## Implementation Verification References

Use these code references as the source of truth when reviewing status:
- `modules/projections.py` (2D projection compute + cache layer)
- `modules/api/routers/embedding.py` (`/api/embedding_map` and `/api/embedding_spaces`)
- `tests/test_api_embedding_map.py` (API behavior and fallback/cache tests)
- `modules/clustering.py` (`_select_best_image` centroid strategy)

Similarity REST routes are defined in `modules/api/routers/` and
[API_CONTRACT.md](../../../technical/API_CONTRACT.md). The retired TODO pointers
route to the Project board; they are not an endpoint inventory.

---

## Remaining Work (True Gaps Only)

### 1) Embedding-map multi-space (App 05, phase 1 — ✅ shipped)
- `compute_embedding_map(embedding_space=…, pca_dim=…)` and `GET /api/embedding_map?space_code=&pca_dim=` route through new helper `modules/projections_db.get_embeddings_with_metadata_for_space`. Both params bake into the disk-cache key.
- PCA pre-step (sklearn) is auto-on for source dim ≥ 1280, off below; `pca_dim=0` disables explicitly.
- `GET /api/similarity/search` now accepts `embedding_space` (REST parity with the MCP tool).
- New `GET /api/images/{image_id}/similar` k-NN endpoint (separate from `/{id}/neighbors`, which stays prev/next nav).
- Coverage in `tests/test_api_embedding_map.py` (multi-space routing, PCA on/off/explicit, unknown space, `/similar` happy + 404).
- Out of scope here (phase 2): persistent projections + HDBSCAN; phase 3: React atlas UI.

### 2) Persistent projections + HDBSCAN (App 05, phase 2 — opt-in)
- First measure whether the disk-cache/recompute path is a bottleneck; keep persistence opt-in.
- Proposed table: `image_embedding_projections` with a deterministic `projection_version`. Allocate a fresh Alembic revision when implementing it: **0013 is already GPS/location**. Mirror DDL under `modules/db_schema/` and update the application-table catalog.
- Add/verify `hdbscan` in the documented GPU-shell environment. Cluster over PCA-50, not 2D.
- Implement `modules/projection_runner.py` as a one-shot job (not a phase) with memory bounds and resume-safe state.
- Proposed endpoint persistence is a new API contract (`persist` is not a current parameter); ship reader/write tests and contract updates before exposing it.

### 3) Electron / Gradio UX Wiring (App 05/07, phase 3)
- Connect existing similarity and embedding-map APIs to production UI flows.
- React atlas (Deck.gl ScatterplotLayer ≥10k points; Plotly fallback below) with color-by selector, side-panel k-NN, and cluster filters.
- `GET /api/embedding_spaces` (✅ shipped) supplies the registry dropdown on the PostgreSQL runtime. Any legacy engine fallback is compatibility code, not a Firebird deployment task. Coverage lives in `tests/test_api_embedding_map.py`.
- Add user-facing interactions for map exploration and "more like this" actions.
- Keep frontend contracts aligned with backend payloads.

### 4) Bidirectional Control Channel (App 08)
- Implement or finalize a robust bi-directional channel so Electron/Gradio can trigger embedding operations and receive live progress/events.

### 5) Headless Orchestration (App 08)
- Complete headless orchestration path for embedding-driven workflows (job triggering, status tracking, and event relay) so UI and automation use the same control surface.

---

## Notes

- App 05 no longer needs to be treated as backend-planned: backend compute + endpoint + tests are in place.
- App 06 centroid representative logic is implemented and should be tracked as complete on backend.
- For App 06, `centroid` and `balanced` strategies use embeddings only when `_select_best_image` receives them (visual stack clustering); burst stack creation currently passes scores only, so those paths fall back to `score` until embeddings are supplied there.
