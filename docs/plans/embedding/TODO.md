# Embedding Features TODO

Backend tasks for embedding-based features. See [NEXT_STEPS.md](NEXT_STEPS.md) for full roadmap.

> See project root [TODO.md](../../../TODO.md) for consolidated list with Electron/DB tags.

## API REST Endpoints (Priority 1)

- [ ] `GET /api/similarity/similar?image_id=123` — Visually similar images across folders
- [ ] `GET /api/similarity/duplicates?folder_path=...` — Near-duplicate pairs
- [ ] `GET /api/similarity/outliers?folder_path=...` — Low neighborhood similarity images

## Clustering & Selection

- [ ] Add `stack_representative_strategy` config option to `ClusteringEngine`
- [ ] Implement centroid strategy (mean embedding → select closest image) in `modules/clustering.py`

## 2D Embedding Map (Priority 2)

- [ ] Add `umap-learn` dependency
- [ ] Implement `modules/projections.py` (UMAP 2D coords + folder-level caching)

## Gradio Integration (Priority 3)

- [ ] Bidirectional WebSocket command channel (see [EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md](EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md))
- [ ] "Similarity Search" tab or context menu in Gradio WebUI using `similar_search.py`
