"""
2D Embedding Map — Application #05

Projects stored MobileNetV2 image embeddings to 2D coordinates using UMAP
(with t-SNE as a fallback when umap-learn is not installed).  Results are
cached on disk as JSON so repeated calls are cheap.

Public API
----------
compute_embedding_map(folder_path, method, refresh, sample_limit, ...) -> dict
invalidate_embedding_map_cache(folder_path) -> int   # returns files deleted
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from modules.config import BASE_DIR, get_config_value

logger = logging.getLogger(__name__)

_CACHE_DIR = BASE_DIR / ".cache" / "embedding_map"
MIN_POINTS = 3  # UMAP / t-SNE require at least 3 samples


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_cache_dir():
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _make_cache_key(folder_path, method, n_neighbors, min_dist):
    """Cache key excludes count so we can check cache before DB query."""
    payload = json.dumps(
        {
            "folder_path": folder_path,
            "method": method,
            "n_neighbors": n_neighbors,
            "min_dist": min_dist,
        },
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode()).hexdigest()


def _cache_path(cache_key):
    return _CACHE_DIR / f"{cache_key}.json"


def _load_cache(cache_key):
    path = _cache_path(cache_key)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read embedding map cache %s: %s", path, exc)
    return None


def _save_cache(cache_key, data):
    _ensure_cache_dir()
    path = _cache_path(cache_key)
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not write embedding map cache %s: %s", path, exc)


def _normalize(matrix):
    """Row-wise L2 normalisation."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _project_umap(vecs, n_neighbors, min_dist):
    import umap  # optional dependency
    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        n_components=2,
        metric="cosine",
        random_state=42,
    )
    return reducer.fit_transform(vecs)


def _project_tsne(vecs, n_neighbors):
    from sklearn.manifold import TSNE

    perplexity = min(n_neighbors, max(5, len(vecs) - 1))
    reducer = TSNE(
        n_components=2,
        metric="cosine",
        perplexity=perplexity,
        random_state=42,
        init="random",
    )
    return reducer.fit_transform(vecs)


def _scale_to_unit(coords):
    """Min-max scale both axes to [0.0, 1.0]."""
    result = coords.astype(float).copy()
    for axis in range(result.shape[1]):
        col = result[:, axis]
        lo, hi = col.min(), col.max()
        span = hi - lo
        result[:, axis] = (col - lo) / span if span > 0 else col * 0.0 + 0.5
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_embedding_map(
    folder_path=None,
    method=None,
    refresh=False,
    sample_limit=None,
    n_neighbors=None,
    min_dist=None,
):
    """
    Project image embeddings to 2D coordinates.

    Parameters
    ----------
    folder_path : str or None
        Scope to a specific folder; None means all images.
    method : {'umap', 'tsne'} or None
        Projection method.  Falls back to config, then 'umap'.
    refresh : bool
        If True, ignore cached result and recompute.
    sample_limit : int or None
        Maximum number of images to include; None means config default.
    n_neighbors : int or None
        UMAP/t-SNE neighbourhood size.  Falls back to config, then 30.
    min_dist : float or None
        UMAP min_dist parameter.  Falls back to config, then 0.1.

    Returns
    -------
    dict
        {
            "points": [{image_id, x, y, file_path, thumbnail_path,
                        label, rating, score_general}, ...],
            "meta":   {count, method, computed_at, cache_key}
        }
        On error: "meta" contains an "error" key and "points" is [].
    """
    method = method or get_config_value("embedding_map.method", "umap")
    n_neighbors = n_neighbors if n_neighbors is not None else get_config_value(
        "embedding_map.n_neighbors", 30
    )
    min_dist = min_dist if min_dist is not None else get_config_value(
        "embedding_map.min_dist", 0.1
    )
    max_points = sample_limit or get_config_value("embedding_map.max_points", 50000)

    from modules import db

    cache_key = _make_cache_key(folder_path, method, n_neighbors, min_dist)
    if not refresh:
        cached = _load_cache(cache_key)
        if cached:
            logger.debug("Embedding map: cache hit %s", cache_key)
            return cached

    rows = db.get_embeddings_with_metadata(folder_path=folder_path, limit=max_points)
    count = len(rows)

    meta_base = {"count": count, "method": method}

    if count < MIN_POINTS:
        logger.info("Embedding map: only %d images — too few to project", count)
        return {
            "points": [],
            "meta": {**meta_base, "error": "too_few_points"},
        }

    # Build embedding matrix
    vecs = np.array(
        [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows],
        dtype=np.float32,
    )
    vecs = _normalize(vecs)

    # Project to 2D
    actual_method = method
    try:
        if method == "umap":
            coords = _project_umap(vecs, n_neighbors, min_dist)
        else:
            coords = _project_tsne(vecs, n_neighbors)
    except ImportError:
        logger.warning("umap-learn not available, falling back to t-SNE")
        actual_method = "tsne"
        coords = _project_tsne(vecs, n_neighbors)

    coords = _scale_to_unit(np.array(coords))

    points = [
        {
            "image_id": r["image_id"],
            "x": float(coords[i, 0]),
            "y": float(coords[i, 1]),
            "file_path": r["file_path"],
            "thumbnail_path": r["thumbnail_path"],
            "label": r["label"],
            "rating": r["rating"],
            "score_general": r["score_general"],
        }
        for i, r in enumerate(rows)
    ]

    result = {
        "points": points,
        "meta": {
            "count": count,
            "method": actual_method,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "cache_key": cache_key,
        },
    }

    _save_cache(cache_key, result)
    logger.info("Embedding map: projected %d images via %s", count, actual_method)
    return result


def invalidate_embedding_map_cache(folder_path=None):
    """
    Delete cached projection files.  Pass folder_path to limit scope (best-effort
    prefix match on the cache filename is not possible; this always clears all
    cached files when folder_path is None, or all files when folder_path is given).

    Returns the number of files deleted.
    """
    if not _CACHE_DIR.exists():
        return 0
    deleted = 0
    for f in _CACHE_DIR.glob("*.json"):
        try:
            f.unlink()
            deleted += 1
        except OSError as exc:
            logger.warning("Could not delete cache file %s: %s", f, exc)
    return deleted
