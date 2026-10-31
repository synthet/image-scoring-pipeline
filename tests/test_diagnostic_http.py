from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.visual_evidence import http
from modules.visual_evidence.cache import EvidenceCache


def test_manifest_is_read_only_and_requests_are_explicit(monkeypatch, tmp_path):
    calls = []
    cache = EvidenceCache(tmp_path)
    manifest = {"image_id": 1, "evidence_schema_version": 2, "layers": {"noise": {"state": "not_requested"}}}
    def read(image_id):
        if image_id != 1:
            raise KeyError(image_id)
        return manifest
    manager = SimpleNamespace(manifest=read, request=lambda image_id, layers, **kw: (calls.append(layers) or dict(manifest, request_id="request")),
                              cancel=lambda image_id, request_id: image_id == 1 and request_id == "request", cache=cache)
    monkeypatch.setattr(http, "get_manager", lambda: manager)
    monkeypatch.setattr(http, "build_evidence_for_image", lambda image_id: SimpleNamespace(model_dump=lambda: {"evidence_schema_version": 1, "image_id": image_id}))
    app = FastAPI()
    app.include_router(http.create_router())
    with TestClient(app) as client:
        assert client.get("/images/1/evidence?schema_version=2").json() == manifest
        assert calls == []
        assert client.get("/images/1/evidence").json()["evidence_schema_version"] == 1
        assert client.get("/images/2/evidence?schema_version=2").status_code == 404
        assert client.post("/images/1/evidence/requests", json={"layers": ["noise"]}).status_code == 202
        assert calls == [["noise"]]
        assert client.post("/images/1/evidence/requests", json={"layers": ["unknown"]}).status_code == 422
        assert client.delete("/images/2/evidence/requests/request").status_code == 404
        assert client.delete("/images/1/evidence/requests/request").status_code == 204
        assert client.get("/images/1/evidence/artifacts/invalid").status_code == 404


def test_artifacts_are_image_scoped_and_immutable(monkeypatch, tmp_path):
    cache = EvidenceCache(tmp_path)
    artifact = cache.write_artifact(1, "a" * 64, b"artifact", "png")
    monkeypatch.setattr(http, "get_manager", lambda: SimpleNamespace(cache=cache))
    app = FastAPI()
    app.include_router(http.create_router())
    with TestClient(app) as client:
        result = client.get(f"/images/1/evidence/artifacts/{artifact}")
        assert result.content == b"artifact"
        assert "immutable" in result.headers["cache-control"]
        assert client.get(f"/images/2/evidence/artifacts/{artifact}").status_code == 404
