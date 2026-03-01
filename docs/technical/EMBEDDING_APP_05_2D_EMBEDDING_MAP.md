# 05 - 2D Embedding Map (Visual Collection Explorer)

*Part of [Possible Applications of image_embedding](EMBEDDING_APPLICATIONS.md).*

## Goal

Provide an interactive 2D map of the image library where spatial proximity reflects visual similarity.

## Why this matters

A map-based view enables fast exploration of large collections, cluster discovery, and gap analysis that are difficult in list/gallery-only interfaces.

## Proposed behavior

Project 1280-d embeddings to 2D using UMAP (or t-SNE fallback), then render a pan/zoom scatter with thumbnails and metadata overlays.

User capabilities:

- zoom into dense clusters,
- filter by folder/label/rating/date,
- click points to open image details,
- run "find similar" from selected point.

## Integration points

- `modules/api.py`
  - Add endpoint: `GET /api/embedding_map`.
- `modules/db.py`
  - Reuse `get_embeddings_for_search(folder_path=...)`.
- UI layer
  - New tab or section in existing stacks workflow.

## API contract (proposal)

Request params:

- `folder_path` (optional)
- `method` (`umap|tsne`, default `umap`)
- `refresh` (bool, default `false`)
- `sample_limit` (optional)

Response:

- `points`: array of `{image_id, x, y, thumbnail_path, label, rating, score_general}`
- `meta`: `{count, method, computed_at, cache_key}`

## Computation pipeline

1. Load embeddings and image metadata.
2. Normalize vectors.
3. Fit dimensionality reduction model.
4. Scale 2D coordinates to viewport space.
5. Cache results by dataset fingerprint.

## Caching strategy

- Key by `(folder_path, embedding_count, newest_updated_at, method, params)`.
- Store map output on disk to avoid expensive recompute.
- Invalidate on re-clustering or mass embedding updates.

## Configuration

- `embedding_map.enabled` (bool, default `false`)
- `embedding_map.method` (`umap`, default)
- `embedding_map.n_neighbors` (int, default `30`)
- `embedding_map.min_dist` (float, default `0.1`)
- `embedding_map.max_points` (int, default `50000`)

## Dependencies

- Primary: `umap-learn`
- Optional fallback: scikit-learn t-SNE

## Edge cases

- Too few points: skip projection and use simple layout.
- Too many points: server-side sampling or level-of-detail aggregation.
- Missing thumbnails: render neutral marker and lazy-load fallback.

## Performance notes

- Projection can be expensive for very large collections.
- Prefer async compute job for large inputs and return cached/partial status.

## Validation plan

- API tests for schema and pagination/sampling.
- UI tests for zoom/filter/selection behaviors.
- Performance profiling on representative large datasets.

## Success metrics

- Acceptable load time for folder-scale views.
- Increased discovery of related images (measured via click-through to detail/similar actions).
- Positive usability feedback compared to baseline gallery browsing.
