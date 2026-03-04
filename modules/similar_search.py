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


def find_near_duplicates(threshold=None, folder_path=None, limit=None):
    """
    Find near-duplicate image pairs in the database based on embedding cosine similarity.
    
    Returns a list of dicts representing near-duplicate pairs, sorted by similarity descending:
        [{'image_id_a': int, 'image_id_b': int, 'file_path_a': str, 'file_path_b': str, 'similarity': float}, ...]
    """
    from modules import config
    
    if threshold is None:
        threshold = config.get_config_value("similarity.duplicate_threshold", 0.98)
    max_pairs = config.get_config_value("similarity.duplicate_max_pairs", 5000)
    
    if limit is None:
        limit = max_pairs
    else:
        limit = min(limit, max_pairs)

    candidates = db.get_embeddings_for_search(folder_path=folder_path)
    if not candidates or len(candidates) < 2:
        return []

    ids = []
    paths = []
    vecs = []
    for cid, cpath, cbytes in candidates:
        ids.append(cid)
        paths.append(cpath)
        vecs.append(np.frombuffer(cbytes, dtype=np.float32))

    matrix = np.stack(vecs)
    matrix_norm = _normalize(matrix)

    n = len(ids)
    results = []
    block_size = 2000
    
    for i in range(0, n, block_size):
        end_i = min(i + block_size, n)
        block_a = matrix_norm[i:end_i]
        
        for j in range(i, n, block_size):
            end_j = min(j + block_size, n)
            block_b = matrix_norm[j:end_j]
            
            sims = block_a @ block_b.T
            
            # Find indices where similarity >= threshold
            rows, cols = np.where(sims >= threshold)
            
            for r, c in zip(rows, cols):
                global_i = i + r
                global_j = j + c
                
                # Only keep upper-triangle (i < j) to avoid self-matches and symmetric duplicates
                if global_i < global_j:
                    results.append({
                        "image_id_a": int(ids[global_i]),
                        "image_id_b": int(ids[global_j]),
                        "file_path_a": paths[global_i],
                        "file_path_b": paths[global_j],
                        "similarity": round(float(sims[r, c]), 6)
                    })
                    
    # Sort by highest similarity first, then deterministic IDs
    results.sort(key=lambda x: (-x['similarity'], x['image_id_a'], x['image_id_b']))
    
    return results[:limit]

