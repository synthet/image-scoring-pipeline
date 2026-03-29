# Embedding Features TODO

Backend tasks for embedding-based features. See [NEXT_STEPS.md](NEXT_STEPS.md) for roadmap + remaining cross-surface work.

> See project root [TODO.md](../../../TODO.md) for consolidated list with Electron/DB tags.

## API REST Endpoints (Priority 1)

- [x] `GET /api/similarity/similar?image_id=123` — Visually similar images across folders
- [x] `GET /api/similarity/duplicates?folder_path=...` — Near-duplicate pairs
- [x] `GET /api/similarity/outliers?folder_path=...` — Low neighborhood similarity images
- [x] `GET /api/embedding_map` — 2D embedding projection endpoint (`modules/api.py` + `modules/projections.py` + `tests/test_api_embedding_map.py`)

## Clustering & Selection

- [x] Add `stack_representative_strategy` config option to `ClusteringEngine`
- [x] Implement centroid strategy (mean embedding → select closest image) in `modules/clustering.py` (`_select_best_image`)

`centroid` / `balanced` apply when that call receives per-image embedding features (visual stacks). Burst stack creation passes scores only today, so representative selection there stays on `score` until embeddings are wired into that path.

## 2D Embedding Map (Priority 2)

- [x] Implement `modules/projections.py` (UMAP/t-SNE 2D coords + folder-level cache)
- [x] Add API-level tests in `tests/test_api_embedding_map.py` (success path, validation, fallback, cache)
- [ ] UI integration in Electron/Gradio for interactive map usage

## Gradio/Electron Integration (Priority 3)

- [x] Bidirectional WebSocket command channel (see [EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md](EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md))
- [ ] Headless orchestration path for embedding workflows (shared trigger/status/event surface)
- [ ] "Similarity Search" tab or context menu in Gradio WebUI using `similar_search.py`

## Verification References

- `modules/projections.py`
- `modules/api.py` (`/api/embedding_map`)
- `tests/test_api_embedding_map.py`
- `modules/clustering.py` (`_select_best_image`)
