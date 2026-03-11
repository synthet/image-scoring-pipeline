# Embedding Features: Next Steps Roadmap

This document summarizes the current implementation status and outlines the prioritized next steps for the 8 proposed embedding applications.

## Status Overview

| App | Feature | Status | Implementation Notes |
|:---|:---|:---|:---|
| 01 | Diversity Selection | **Implemented** | `diversity.py` (MMR) integrated in `selection.py`. |
| 02 | Near-Duplicate Detection | **Implemented** | `similar_search.py` (`find_near_duplicates`). |
| 03 | Tag Propagation | **Implemented** | `tagging.py` (`propagate_tags`). |
| 04 | Outlier Detection | **Implemented** | `similar_search.py` (`find_outliers`). |
| 05 | 2D Embedding Map | **Planned** | Needs `umap-learn`, REST endpoint, and UI. |
| 06 | Smart Stack Representative | **Partial** | Needs Centroid-based logic in `ClusteringEngine`. |
| 07 | "More Like This" UI | **Partial** | Search logic exists; needs REST API and UI wiring. |
| 08 | Gradio Integration | **Planned** | Major architectural task (WebSockets, Headless). |

---

## Priority 1: Backend Infrastructure (Short Term)

### 1.1 API REST Endpoints
Implement the following endpoints in `modules/api.py` to expose existing embedding logic to the Electron frontend and Gradio UI:
- `GET /api/similarity/similar?image_id=123`: Returns visually similar images across folders.
- `GET /api/similarity/duplicates?folder_path=...`: Returns pairs of near-duplicates.
- `GET /api/similarity/outliers?folder_path=...`: Returns a list of images with low neighborhood similarity scores.

### 1.2 Clustering Refinement
Update the `ClusteringEngine` in `modules/clustering.py`:
- Add a configuration option for `stack_representative_strategy`.
- Implement `centroid` strategy which calculates the mean embedding for a cluster and selects the image with the minimum cosine distance to that mean.

---

## Priority 2: 2D Exploratory Map (Medium Term)

### 2.1 Dependencies
Add `umap-learn` to the environment. Note that UMAP requires `numpy`, `scipy`, and `scikit-learn` (already present).

### 2.2 Computation & Caching
Implement `modules/projections.py`:
- Function to compute 2D coordinates for a batch of images using UMAP.
- Layer a caching mechanism (disk-based) to store projections at the folder level to avoid re-computation.

---

## Priority 3: Architecture & UI Integration (Long Term)

### 3.1 Headless Mode & WebSocket Relay
As per [App 08](EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md), implement the bi-directional command channel to allow the Electron app to trigger embedding operations and receive real-time updates.

### 3.2 Gradio Similarity Search
Add a "Similarity Search" tab or context menu in the Gradio WebUI that uses the `similar_search.py` module to browse the collection visually.

---

## Conclusion
The groundwork for embeddings is largely solid. The immediate focus should be **API exposure** and **Smart Representative** logic to make the existing features actionable from the UI.
