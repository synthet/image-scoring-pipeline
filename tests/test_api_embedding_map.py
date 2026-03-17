"""
Tests for GET /api/embedding_map endpoint.

All tests are pure-unit: they mock db.get_embeddings_with_metadata and the
projection functions so no GPU, Firebird, or umap-learn dependency is required.
"""

import numpy as np
import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from modules import api
except ImportError as e:
    pytest.skip(f"API deps not available: {e}", allow_module_level=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_client():
    app = FastAPI()
    app.include_router(api.create_api_router())
    return TestClient(app)


def _fake_rows(n, dim=8):
    """Return n fake embedding rows with random float32 vectors of dimension `dim`."""
    rows = []
    rng = np.random.default_rng(0)
    for i in range(n):
        vec = rng.random(dim).astype(np.float32)
        rows.append({
            "image_id": i + 1,
            "file_path": f"/photos/img{i+1:04d}.jpg",
            "embedding": vec.tobytes(),
            "thumbnail_path": f"/thumbs/img{i+1:04d}.jpg",
            "label": None,
            "rating": None,
            "score_general": round(float(rng.random()), 3),
        })
    return rows


def _fake_coords(n):
    """Return deterministic 2D coords for n points."""
    rng = np.random.default_rng(1)
    return rng.random((n, 2)).astype(np.float64)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_embedding_map_too_few_points(monkeypatch):
    """Fewer than 3 images → success=True but points=[] and error key present."""
    import modules.db as db_mod

    monkeypatch.setattr(db_mod, "get_embeddings_with_metadata", lambda **kw: _fake_rows(1))

    with _build_client() as client:
        resp = client.get("/api/embedding_map")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["points"] == []
    assert data["meta"]["error"] == "too_few_points"


def test_embedding_map_returns_points(monkeypatch):
    """With enough rows the endpoint returns a point per image."""
    import modules.db as db_mod
    import modules.projections as proj_mod

    n = 5
    rows = _fake_rows(n)
    monkeypatch.setattr(db_mod, "get_embeddings_with_metadata", lambda **kw: rows)

    fixed_coords = _fake_coords(n)

    def _fake_project_umap(vecs, n_neighbors, min_dist):
        return fixed_coords

    monkeypatch.setattr(proj_mod, "_project_umap", _fake_project_umap)
    # Ensure cache is bypassed
    monkeypatch.setattr(proj_mod, "_load_cache", lambda key: None)
    monkeypatch.setattr(proj_mod, "_save_cache", lambda key, data: None)

    with _build_client() as client:
        resp = client.get("/api/embedding_map?method=umap")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    points = body["data"]["points"]
    assert len(points) == n
    # All required fields present
    for pt in points:
        for field in ("image_id", "x", "y", "file_path", "thumbnail_path",
                      "label", "rating", "score_general"):
            assert field in pt, f"Missing field: {field}"
    # x/y are in [0, 1]
    for pt in points:
        assert 0.0 <= pt["x"] <= 1.0
        assert 0.0 <= pt["y"] <= 1.0
    # meta fields present
    meta = body["data"]["meta"]
    assert meta["count"] == n
    assert meta["method"] == "umap"
    assert "computed_at" in meta
    assert "cache_key" in meta


def test_embedding_map_invalid_method():
    """Unsupported method value → 422 Unprocessable Entity."""
    with _build_client() as client:
        resp = client.get("/api/embedding_map?method=foo")
    assert resp.status_code == 422


def test_embedding_map_tsne_fallback(monkeypatch):
    """When umap raises ImportError, t-SNE is used and meta.method == 'tsne'."""
    import modules.db as db_mod
    import modules.projections as proj_mod

    n = 5
    rows = _fake_rows(n)
    monkeypatch.setattr(db_mod, "get_embeddings_with_metadata", lambda **kw: rows)

    def _raise_import(vecs, n_neighbors, min_dist):
        raise ImportError("umap-learn not installed")

    fixed_coords = _fake_coords(n)

    def _fake_project_tsne(vecs, n_neighbors):
        return fixed_coords

    monkeypatch.setattr(proj_mod, "_project_umap", _raise_import)
    monkeypatch.setattr(proj_mod, "_project_tsne", _fake_project_tsne)
    monkeypatch.setattr(proj_mod, "_load_cache", lambda key: None)
    monkeypatch.setattr(proj_mod, "_save_cache", lambda key, data: None)

    with _build_client() as client:
        resp = client.get("/api/embedding_map?method=umap")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["meta"]["method"] == "tsne"
    assert len(body["data"]["points"]) == n


def test_embedding_map_cache_hit(monkeypatch):
    """When cache returns data, db and projection are not called."""
    import modules.db as db_mod
    import modules.projections as proj_mod

    cached_data = {
        "points": [{"image_id": 1, "x": 0.5, "y": 0.5, "file_path": "/a.jpg",
                    "thumbnail_path": None, "label": None, "rating": None,
                    "score_general": 0.9}],
        "meta": {"count": 1, "method": "umap", "computed_at": "2026-01-01T00:00:00+00:00",
                 "cache_key": "abc123"},
    }

    db_called = {"flag": False}

    def _fail_db(**kw):
        db_called["flag"] = True
        return []

    monkeypatch.setattr(db_mod, "get_embeddings_with_metadata", _fail_db)
    monkeypatch.setattr(proj_mod, "_load_cache", lambda key: cached_data)

    with _build_client() as client:
        resp = client.get("/api/embedding_map")

    assert resp.status_code == 200
    # DB should NOT have been called — cache short-circuited
    assert not db_called["flag"]
    assert resp.json()["data"] == cached_data
