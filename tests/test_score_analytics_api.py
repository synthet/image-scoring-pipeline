"""FastAPI tests for score analytics routes (DB loader patched; one optional DB smoke test)."""

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules import api, config
from modules.score_analytics import data


def _fixture_rows(n: int = 200, seed: int = 0):
    rng = np.random.default_rng(seed)
    liqe = rng.random(n)
    spaq = np.clip(liqe + rng.normal(0, 0.1, n), 0, 1)
    claude = rng.random(n)
    general = 0.6 * liqe + 0.4 * spaq
    image_rows = [
        (i + 1, float(general[i]), None if i % 10 == 0 else 0.5, None, i // 5 + 1, 1 if i % 5 == 0 else 0)
        for i in range(n)
    ]
    score_rows = []
    for i in range(n):
        score_rows.append((i + 1, "liqe", float(liqe[i]), False))
        if i % 4:
            score_rows.append((i + 1, "spaq", float(spaq[i]), False))
        score_rows.append((i + 1, "claude", float(claude[i]), True))
    return image_rows, score_rows


@pytest.fixture
def patched(monkeypatch):
    image_rows, score_rows = _fixture_rows()
    calls = {"load": 0}

    def fake_load(fp):
        calls["load"] += 1
        return data.build_matrix(image_rows, score_rows, fp, [(1, 1), (2, 7)])

    monkeypatch.setattr(data, "require_postgres", lambda: None)
    monkeypatch.setattr(data, "keyword_image_ids", lambda kw: np.arange(1, 101) if kw == "bird" else np.array([]))
    monkeypatch.setattr(data, "top_keywords", lambda limit, min_images: [("bird", 100)])
    monkeypatch.setattr(data, "_query_fingerprint", lambda: "fp-test")
    monkeypatch.setattr(data, "_load_from_db", fake_load)
    data.reset_cache()
    yield calls
    data.reset_cache()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api.create_api_router())
    return TestClient(app)


def test_routes_registered():
    paths = {r.path for r in api.create_api_router().routes}
    assert {
        "/api/analytics/scores/matrix",
        "/api/analytics/scores/stats",
        "/api/analytics/scores/regression",
        "/api/analytics/scores/stacks",
        "/api/analytics/scores/keywords",
    } <= paths


def test_build_matrix_orders_and_pivots():
    image_rows, score_rows = _fixture_rows(20)
    m = data.build_matrix(image_rows, score_rows, "x")
    assert m.keys == ["general", "technical", "liqe", "spaq", "claude"]
    assert m.meta["claude"]["kind"] == "shadow"
    assert m.meta["technical"]["count"] == 18
    assert m.meta["spaq"]["count"] == 15
    assert np.isnan(m.series["spaq"][0])
    assert m.stack_ids[:6].tolist() == [1, 1, 1, 1, 1, 2]
    assert m.pick_status[:6].tolist() == [1, 0, 0, 0, 0, 1]


def test_matrix_endpoint_etag_and_cache(client, patched):
    r = client.get("/api/analytics/scores/matrix")
    assert r.status_code == 200
    body = r.json()
    assert body["image_count"] == 200
    assert body["keys"] == ["general", "technical", "liqe", "spaq", "claude"]
    assert len(body["series"]["liqe"]) == 200
    assert body["series"]["spaq"][0] is None
    assert body["meta"]["claude"]["kind"] == "shadow"
    assert r.headers["content-encoding"] == "gzip"
    etag = r.headers["etag"]

    r2 = client.get("/api/analytics/scores/matrix", headers={"If-None-Match": etag})
    assert r2.status_code == 304

    r3 = client.get("/api/analytics/scores/matrix", headers={"Accept-Encoding": "identity"})
    assert r3.status_code == 200
    assert "content-encoding" not in r3.headers
    assert r3.json()["image_count"] == 200
    assert patched["load"] == 1


def test_stats_endpoint(client, patched):
    r = client.get("/api/analytics/scores/stats")
    assert r.status_code == 200
    body = r.json()
    keys = body["keys"]
    i, j = keys.index("liqe"), keys.index("spaq")
    assert body["correlation"]["pearson"][i][j] > 0.8
    assert body["correlation"]["n"][i][j] == 150
    assert body["descriptives"]["liqe"]["count"] == 200
    assert len(body["descriptives"]["liqe"]["histogram"]["counts"]) == 50


def test_regression_endpoint(client, patched):
    r = client.get("/api/analytics/scores/regression", params={"target": "general", "predictors": "liqe,spaq"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["complete_rows"] == 150
    coef = {c["name"]: c for c in body["coefficients"]}
    assert coef["liqe"]["beta"] == pytest.approx(0.6, abs=1e-6)
    assert coef["spaq"]["beta"] == pytest.approx(0.4, abs=1e-6)
    assert body["r2"] == pytest.approx(1.0)
    assert body["recommendations"]

    default = client.get("/api/analytics/scores/regression").json()
    assert default["predictors"] == ["liqe", "spaq"]  # shadow + composites excluded


def test_keyword_scope(client, patched):
    stats_body = client.get("/api/analytics/scores/stats", params={"keyword": " Bird "}).json()
    assert stats_body["scope"] == {"kind": "keyword", "keyword": "bird"}
    assert stats_body["image_count"] == 100
    matrix = client.get("/api/analytics/scores/matrix", params={"keyword": "bird"})
    assert matrix.json()["image_count"] == 100
    assert matrix.headers["etag"] != client.get("/api/analytics/scores/matrix").headers["etag"]
    empty = client.get("/api/analytics/scores/stats", params={"keyword": "nothing"}).json()
    assert empty["image_count"] == 0 and empty["keys"] == []
    reg = client.get("/api/analytics/scores/regression", params={"keyword": "bird", "predictors": "liqe"})
    assert reg.status_code == 200 and reg.json()["complete_rows"] == 100


def test_stacks_endpoint(client, patched):
    r = client.get("/api/analytics/scores/stacks")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stacks_considered"] == 40
    assert body["stacks_with_picks"] == 40
    models = {m["dimension"]: m for m in body["models"]}
    assert models["liqe"]["pick_pairs"] == 40 * 4
    assert models["general"]["best_stacks"] == 2
    assert set(body["ranking"]) <= set(body["keys"])
    assert client.get("/api/analytics/scores/stacks", params={"min_size": 1}).status_code == 422


def test_keyword_profiles_endpoint(client, patched):
    body = client.get("/api/analytics/scores/keywords").json()
    assert body["keywords"][0]["keyword"] == "bird"
    dims = {d["dimension"]: d for d in body["keywords"][0]["dimensions"]}
    assert dims["liqe"]["count"] == 100
    assert "cohens_d" in dims["liqe"]


@pytest.mark.parametrize(
    "params",
    [
        {"target": "nope"},
        {"target": "general", "predictors": "liqe,unknown"},
        {"target": "general", "predictors": "general,liqe"},
    ],
)
def test_regression_rejects_bad_input(client, patched, params):
    assert client.get("/api/analytics/scores/regression", params=params).status_code == 422


def test_non_postgres_returns_501(client, monkeypatch):
    monkeypatch.setattr(config, "get_database_engine", lambda: "firebird")
    data.reset_cache()
    assert client.get("/api/analytics/scores/stats").status_code == 501


@pytest.mark.db
def test_score_analytics_live_smoke(client):
    if config.get_database_engine() != "postgres":
        pytest.skip("PostgreSQL required")
    data.reset_cache()
    resp = client.get("/api/analytics/scores/stats")
    if resp.status_code == 501:
        pytest.skip("Analytics not on postgres in this environment")
    assert resp.status_code == 200
    assert "descriptives" in resp.json()
