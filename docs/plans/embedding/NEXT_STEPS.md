# Embedding Features: Next Steps Roadmap

This document summarizes the current implementation status and the **true remaining gaps** for the 8 proposed embedding applications.

## Status Overview

| App | Feature | Status | Implementation Notes |
|:---|:---|:---|:---|
| 01 | Diversity Selection | **Implemented** | `diversity.py` (MMR) integrated in `selection.py`. |
| 02 | Near-Duplicate Detection | **Implemented** | `similar_search.py` (`find_near_duplicates`). |
| 03 | Tag Propagation | **Implemented** | `tagging.py` (`propagate_tags`). |
| 04 | Outlier Detection | **Implemented** | `similar_search.py` (`find_outliers`). |
| 05 | 2D Embedding Map | **Backend Implemented / UI Partial** | Projection service exists in `modules/projections.py`; API exposed at `GET /api/embedding_map`; coverage in `tests/test_api_embedding_map.py`. UI/Electron wiring may still be pending. |
| 06 | Smart Stack Representative | **Implemented** | Centroid representative selection is implemented in `modules/clustering.py` (`_select_best_image`, `stack_representative_strategy`). |
| 07 | "More Like This" UI | **Partial** | Search logic and REST API exist; UI wiring is still needed. |
| 08 | Gradio Integration | **Partial** | Backend APIs exist, but bidirectional control and orchestration work remain. |

---

## Implementation Verification References

Use these code references as the source of truth when reviewing status:
- `modules/projections.py` (2D projection compute + cache layer)
- `modules/api.py` (`/api/embedding_map` route)
- `tests/test_api_embedding_map.py` (API behavior and fallback/cache tests)
- `modules/clustering.py` (`_select_best_image` centroid strategy)

Similarity REST routes (search, duplicates, outliers) are tracked in [TODO.md](TODO.md) under **API REST Endpoints**; request/response shapes are described in [API_CONTRACT.md](../../technical/API_CONTRACT.md).

---

## Remaining Work (True Gaps Only)

### 1) Electron / Gradio UX Wiring
- Connect existing similarity and embedding-map APIs to production UI flows.
- Add user-facing interactions for map exploration and "more like this" actions.
- Keep frontend contracts aligned with backend payloads.

### 2) Bidirectional Control Channel
- Implement or finalize a robust bi-directional channel (per App 08 plan) so Electron/Gradio can trigger embedding operations and receive live progress/events.

### 3) Headless Orchestration
- Complete headless orchestration path for embedding-driven workflows (job triggering, status tracking, and event relay) so UI and automation use the same control surface.

---

## Notes

- App 05 no longer needs to be treated as backend-planned: backend compute + endpoint + tests are in place.
- App 06 centroid representative logic is implemented and should be tracked as complete on backend.
- For App 06, `centroid` and `balanced` strategies use embeddings only when `_select_best_image` receives them (visual stack clustering); burst stack creation currently passes scores only, so those paths fall back to `score` until embeddings are supplied there.
