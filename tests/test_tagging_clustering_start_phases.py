"""The legacy single-phase /start endpoints enqueue their full dependency prefix.

Guards against the "index + tags, no score" regression: these legacy single-phase
endpoints must expand to their contiguous pipeline prefix so keywords/culling can
never be marked done while metadata/scoring stay not_started.

Prefix expansion is also *why* these endpoints are not subject to the Gate 1
prerequisite check that /api/runs/submit and /api/pipeline/submit apply: their
effective plan is the whole prefix, which satisfies its own prerequisites by
construction, so the gate could never reject. See issue #365.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules import api, db


class _RunnerStub:
    is_running = False

    def stop(self):
        return None


def _build_client():
    app = FastAPI()
    app.include_router(api.create_api_router())
    return TestClient(app)


def _capture_phases(monkeypatch):
    captured = {}

    def fake_enqueue_job(input_path, phase_code, job_type=None, queue_payload=None, description=None):
        captured["phase_code"] = phase_code
        return 777, 1

    def fake_create_job_phases(job_id, phases_list, first_phase_state="queued", *a, **k):
        captured["phases"] = list(phases_list)
        return []

    monkeypatch.setattr(db, "enqueue_job", fake_enqueue_job)
    monkeypatch.setattr(db, "create_job_phases", fake_create_job_phases)
    monkeypatch.setattr(
        api, "resolve_selectors", lambda **kwargs: {"resolved_image_ids": [1, 2, 3]}
    )
    return captured


def test_tagging_start_enqueues_full_prefix(monkeypatch):
    monkeypatch.setattr(api, "_tagging_runner", _RunnerStub())
    captured = _capture_phases(monkeypatch)

    with _build_client() as client:
        response = client.post("/api/tagging/start", json={"image_ids": [1, 2, 3]})

    assert response.status_code == 200, response.text
    assert captured["phase_code"] == "keywords"
    assert captured["phases"] == ["indexing", "metadata", "scoring", "keywords"]


def test_clustering_start_enqueues_full_prefix(monkeypatch):
    monkeypatch.setattr(api, "_clustering_runner", _RunnerStub())
    monkeypatch.setattr("modules.ui.security._check_rate_limit", lambda *a, **k: None)
    captured = _capture_phases(monkeypatch)

    with _build_client() as client:
        response = client.post("/api/clustering/start", json={"image_ids": [1, 2, 3]})

    assert response.status_code == 200, response.text
    assert captured["phase_code"] == "culling"
    # culling prefix excludes keywords (sibling under scoring).
    assert captured["phases"] == ["indexing", "metadata", "scoring", "culling"]


def test_scoring_start_enqueues_derived_prefix(monkeypatch):
    """Was a hardcoded ["indexing","metadata","scoring"]; now derived from the DAG."""
    monkeypatch.setattr(api, "_scoring_runner", _RunnerStub())
    monkeypatch.setattr("modules.ui.security._check_rate_limit", lambda *a, **k: None)
    captured = _capture_phases(monkeypatch)

    with _build_client() as client:
        response = client.post("/api/scoring/start", json={"image_ids": [1, 2, 3]})

    assert response.status_code == 200, response.text
    assert captured["phase_code"] == "scoring"
    assert captured["phases"] == ["indexing", "metadata", "scoring"]


def test_bird_species_start_enqueues_full_prefix(monkeypatch):
    """Regression for #365: this endpoint queued ["bird_species"] with phase_code=None.

    A run whose plan names only the terminal phase has no upstream stages at all --
    unlike its three sibling /start endpoints, which have expanded their prefix since
    the control-plane consolidation.
    """
    monkeypatch.setattr(api, "_bird_species_runner", _RunnerStub())
    monkeypatch.setattr("modules.ui.security._check_rate_limit", lambda *a, **k: None)
    captured = _capture_phases(monkeypatch)

    with _build_client() as client:
        response = client.post("/api/bird-species/start", json={"image_ids": [1, 2, 3]})

    assert response.status_code == 200, response.text
    assert captured["phase_code"] == "bird_species"
    assert captured["phases"] == [
        "indexing", "metadata", "scoring", "keywords", "bird_species",
    ]
