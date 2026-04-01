# Image embeddings (MobileNetV2, Postgres, backfill)

## What is stored

- **Column:** `images.image_embedding` (PostgreSQL: `vector(1280)` via pgvector; legacy Firebird: BLOB float32 payload).
- **Model:** TensorFlow Keras **MobileNetV2**, ImageNet weights, `include_top=False`, global average pooling → **1280** floats.
- **Semantics:** Coarse **visual similarity** features for clustering, near-duplicate-style retrieval, tag propagation neighbors, and similar-image search. They are **not** CLIP text–image aligned embeddings.

## When embeddings are written

1. **Culling phase (clustering)** — [`modules/clustering.py`](../../modules/clustering.py) `ClusteringEngine.extract_features()` persists batches with `db.update_image_embeddings_batch()`. Algorithm/model identity is tracked in code as `CLUSTER_VERSION` in that module.
2. **On demand** — [`modules/similar_search.py`](../../modules/similar_search.py) may compute and persist a single embedding via `ClusteringEngine` if an image is queried and `image_embedding` is null.

## Backfill images missing embeddings

Run in **WSL** with **`~/.venvs/tf`** (same as the web UI), with paths to thumbnails or originals resolvable from WSL.

**Canonical Windows one-launcher:**

```text
scripts\maintenance\run_populate_embeddings.bat
```

Optional arguments are passed through to Python, for example:

```text
run_populate_embeddings.bat --dry-run
run_populate_embeddings.bat --limit 500
run_populate_embeddings.bat --folder "D:\Photos\Trip"
run_populate_embeddings.bat --resume-after-id 12345
```

**Direct Python (WSL):**

```bash
python scripts/maintenance/populate_missing_embeddings.py [--dry-run] [--limit N] [--folder PATH] [--batch-size N] [--resume-after-id ID]
```

**Legacy launcher name:** `run_populate_missing_embeddings.bat` calls the same script (backward-compatible).

## Schema: column on `images` vs separate table

For a **single** embedding type (fixed model and dimension), keeping **`images.image_embedding`** is appropriate: one vector per image, HNSW index on Postgres, no join on every similarity query.

Introduce a separate table (e.g. `image_embeddings` keyed by `image_id` + `model_key`) only if you need **multiple models**, **explicit versioning/invalidation**, or **independent lifecycle** from the image row. pgvector columns have a **fixed dimension per column**; multiple dimensions usually mean multiple columns or multiple tables, each with `vector(N)` and its own index.

## Checklist for additional models (e.g. CLIP)

If you add another stored vector, define up front:

| Field | Example |
|-------|---------|
| Model identity | `mobilenet_v2_imagenet_gap`, `clip_vit_b32_image` |
| Dimension `N` for `vector(N)` | 1280 vs 512, etc. |
| Semantic use | CNN visual vs CLIP image tower vs text |
| Version | Tie to `CLUSTER_VERSION`, HF revision, or weights hash |
| Indexes | Separate HNSW (or IVFFlat) per query pattern |
| API / callers | Which endpoints and MCP tools read which space |

Treat a new space as **not interchangeable** with MobileNet embeddings without migration, reindex, and caller updates.

## Related code

- [`modules/clustering.py`](../../modules/clustering.py) — feature extraction and culling persistence
- [`modules/similar_search.py`](../../modules/similar_search.py) — similarity search, `EMBEDDING_DIM`
- [`modules/db.py`](../../modules/db.py) — `update_image_embedding(s)`, `get_images_missing_embeddings`
- [`modules/db_postgres.py`](../../modules/db_postgres.py) — `vector(1280)` DDL and HNSW index
- [`scripts/maintenance/populate_missing_embeddings.py`](../../scripts/maintenance/populate_missing_embeddings.py) — backfill CLI
