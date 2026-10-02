"""Score analytics hides legacy/research dimensions by default (#477). No DB."""

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules import api
from modules.score_analytics import data

LEGACY = {"koniq", "paq2piq", "refcull_eye"}


def _rows(n: int = 120, seed: int = 1):
    rng = np.random.default_rng(seed)
    image_rows = [(i + 1, float(rng.random()), None, None, i // 4 + 1, 1 if i % 4 == 0 else 0) for i in range(n)]
    score_rows = []
    for i in range(n):
        for name, shadow in (("liqe", False), ("spaq", False), ("koniq", False), ("paq2piq", False), ("refcull_eye", True)):
            score_rows.append((i + 1, name, float(rng.random()), shadow))
    return image_rows, score_rows


@pytest.fixture
def patched(monkeypatch):
    image_rows, score_rows = _rows()
    monkeypatch.setattr(data, "require_postgres", lambda: None)
    monkeypatch.setattr(data, "keyword_image_ids", lambda kw: np.arange(1, 61))
    monkeypatch.setattr(data, "top_keywords", lambda limit, min_images: [("bird", 60)])
    monkeypatch.setattr(data, "_query_fingerprint", lambda: "fp-legacy")
    monkeypatch.setattr(data, "_load_from_db", lambda fp: data.build_matrix(image_rows, score_rows, fp))
    data.reset_cache()
    yield
    data.reset_cache()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api.create_api_router())
    return TestClient(app)


def test_is_legacy_dim():
    assert all(data.is_legacy_dim(k) for k in LEGACY)
    assert not any(data.is_legacy_dim(k) for k in ("liqe", "general", "clip_quality_v0"))


def test_drop_legacy_keeps_rows_and_active_dims():
    m = data.build_matrix(*_rows(8), "x")
    d = data.drop_legacy(m)
    assert d.keys == ["general", "liqe", "spaq"]
    assert set(d.series) == set(d.meta) == set(d.keys)
    assert d.image_count == m.image_count
    assert "koniq" in m.keys  # source matrix untouched


@pytest.mark.parametrize("keyword", [None, "bird"])
def test_get_scoped_default_hides_legacy(patched, keyword):
    assert not LEGACY & set(data.get_scoped(keyword).keys)
    assert LEGACY <= set(data.get_scoped(keyword, include_legacy=True).keys)


def test_matrix_endpoint_param_and_etag(client, patched):
    r0 = client.get("/api/analytics/scores/matrix")
    r1 = client.get("/api/analytics/scores/matrix", params={"include_legacy": "true"})
    assert not LEGACY & set(r0.json()["keys"])
    assert LEGACY <= set(r1.json()["keys"])
    assert r0.headers["etag"] != r1.headers["etag"]


@pytest.mark.parametrize(
    "path, keys_of",
    [
        ("/api/analytics/scores/stats", lambda j: set(j["keys"])),
        ("/api/analytics/scores/keywords", lambda j: set(j["keys"])),
        ("/api/analytics/scores/stacks", lambda j: set(j["meta"])),
        ("/api/analytics/scores/regression", lambda j: set(j["predictors"])),
    ],
)
def test_endpoints_hide_legacy_unless_requested(client, patched, path, keys_of):
    r0 = client.get(path)
    r1 = client.get(path, params={"include_legacy": "true"})
    assert r0.status_code == r1.status_code == 200, (r0.text, r1.text)
    assert not LEGACY & keys_of(r0.json())
    assert LEGACY & keys_of(r1.json())


def test_regression_explicit_legacy_predictor_needs_flag(client, patched):
    path = "/api/analytics/scores/regression"
    assert client.get(path, params={"predictors": "koniq"}).status_code == 422
    assert client.get(path, params={"predictors": "koniq", "include_legacy": "true"}).status_code == 200
