"""
Similar Image Search

Finds visually similar images using stored MobileNetV2 embeddings
and cosine similarity ranking.
"""

import logging
import numpy as np
from modules import db

logger = logging.getLogger(__name__)


def _normalize(v):
    """L2-normalize a vector (or row-wise for a matrix)."""
    if v.ndim == 1:
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else v
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return v / norms


def _get_or_compute_embedding(image_id, file_path=None):
    """
    Return the embedding for an image, computing and persisting it
    on the fly if not already stored in the DB.
    """
    emb_bytes = db.get_image_embedding(image_id)
    if emb_bytes is not None:
        return np.frombuffer(emb_bytes, dtype=np.float32)

    if not file_path:
        conn = db.get_db()
        c = conn.cursor()
        try:
            c.execute("SELECT file_path FROM images WHERE id = ?", (image_id,))
            row = c.fetchone()
            file_path = row[0] if row else None
        finally:
            conn.close()
        if not file_path:
            return None

    from modules.clustering import ClusteringEngine
    engine = ClusteringEngine()
    features, valid = engine.extract_features([file_path])
    if len(features) == 0:
        return None

    vec = features[0].astype(np.float32)
    db.update_image_embedding(image_id, vec.tobytes())
    return vec


def search_similar_images(example_path=None, example_image_id=None,
                          limit=20, folder_path=None, min_similarity=None):
    """
    Find images most visually similar to a given example.

    Provide either example_path (file path string) or example_image_id (int).
    Returns a list of dicts sorted by descending similarity.
    """
    if not example_path and example_image_id is None:
        return {"error": "Provide example_path or example_image_id"}

    # Resolve the example image
    if example_path:
        details = db.get_image_details(example_path)
        if not details or not details.get('id'):
            return {"error": f"Image not found in database: {example_path}"}
        example_image_id = details['id']
        file_path = example_path
    else:
        conn = db.get_db()
        c = conn.cursor()
        try:
            c.execute("SELECT file_path FROM images WHERE id = ?", (example_image_id,))
            row = c.fetchone()
            file_path = row[0] if row else None
        finally:
            conn.close()

    query_vec = _get_or_compute_embedding(example_image_id, file_path)
    if query_vec is None:
        return {"error": "Could not obtain embedding for the example image"}

    candidates = db.get_embeddings_for_search(folder_path=folder_path)
    if not candidates:
        return {"error": "No embeddings found in database. Run clustering first to populate embeddings."}

    ids = []
    paths = []
    vecs = []
    for cid, cpath, cbytes in candidates:
        if cid == example_image_id:
            continue
        ids.append(cid)
        paths.append(cpath)
        vecs.append(np.frombuffer(cbytes, dtype=np.float32))

    if not vecs:
        return []

    candidate_matrix = np.stack(vecs)
    query_norm = _normalize(query_vec)
    candidate_norm = _normalize(candidate_matrix)
    similarities = candidate_norm @ query_norm

    order = np.argsort(-similarities)
    results = []
    for idx in order:
        sim = float(similarities[idx])
        if min_similarity is not None and sim < min_similarity:
            break
        results.append({
            "image_id": int(ids[idx]),
            "file_path": paths[idx],
            "similarity": round(sim, 6),
        })
        if len(results) >= limit:
            break

    return results
