from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules import api, db
from modules.ui import app as ui_app


class _RunnerStub:
    is_running = False


def _build_client():
    app = FastAPI()
    app.include_router(api.create_api_router())
    return TestClient(app)


def test_jobs_queue_endpoint_refreshes_from_db_with_limit_zero(monkeypatch):
    monkeypatch.setattr(api._job_dispatcher, "get_state", lambda: {
        "queue": [{"id": 999, "queue_position": 1}],
        "queue_size": 1,
        "active_runner": None,
        "is_dispatcher_running": True,
    })

    calls = []

    def fake_get_queued_jobs(limit=200):
        calls.append(limit)
        return []

    monkeypatch.setattr(db, "get_queued_jobs", fake_get_queued_jobs)

    with _build_client() as client:
        response = client.get("/api/jobs/queue", params={"limit": 0})

    assert response.status_code == 200
    payload = response.json()
    assert calls == [0]
    assert payload["queue"] == []
    assert payload["queue_size"] == 0


def test_pipeline_submit_cluster_enqueues_full_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_app, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_clustering_runner", _RunnerStub())

    captured = {}

    def fake_enqueue_job(input_path, phase_code, job_type=None, queue_payload=None):
        captured["input_path"] = input_path
        captured["phase_code"] = phase_code
        captured["job_type"] = job_type
        captured["queue_payload"] = queue_payload
        return 321, 7

    monkeypatch.setattr(db, "enqueue_job", fake_enqueue_job)

    created_phase_codes = {}

    def fake_create_job_phases(job_id, phase_codes):
        created_phase_codes["job_id"] = job_id
        created_phase_codes["phase_codes"] = list(phase_codes)
        return [
            {"phase_order": idx, "phase_code": code, "state": "running" if idx == 0 else "pending"}
            for idx, code in enumerate(phase_codes)
        ]

    monkeypatch.setattr(db, "create_job_phases", fake_create_job_phases)

    body = {
        "input_path": str(tmp_path),
        "operations": ["cluster"],
        "clustering_threshold": 0.2,
        "clustering_time_gap": 12,
        "clustering_force_rescan": True,
    }

    with _build_client() as client:
        response = client.post("/api/pipeline/submit", json=body)

    assert response.status_code == 200
    result = response.json()
    assert result["success"] is True
    assert result["data"]["queue_position"] == 7

    assert captured["phase_code"] == "culling"
    assert captured["job_type"] == "clustering"
    assert captured["queue_payload"] == {
        "input_path": str(tmp_path),
        "threshold": 0.2,
        "time_gap": 12,
        "force_rescan": True,
    }
    assert created_phase_codes["job_id"] == 321
    assert created_phase_codes["phase_codes"] == ["culling"]


def test_scoring_start_returns_500_when_enqueue_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_app, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_scoring_runner", _RunnerStub())
    monkeypatch.setattr(db, "enqueue_job", lambda *args, **kwargs: (None, 0))

    with _build_client() as client:
        response = client.post("/api/scoring/start", json={"input_path": str(tmp_path)})

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to enqueue scoring job"


def test_tagging_start_returns_500_when_enqueue_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_app, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_tagging_runner", _RunnerStub())
    monkeypatch.setattr(db, "enqueue_job", lambda *args, **kwargs: (None, 0))

    with _build_client() as client:
        response = client.post("/api/tagging/start", json={"input_path": str(tmp_path)})

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to enqueue tagging job"


def test_clustering_start_returns_500_when_enqueue_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_app, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_clustering_runner", _RunnerStub())
    monkeypatch.setattr(db, "enqueue_job", lambda *args, **kwargs: (None, 0))

    with _build_client() as client:
        response = client.post("/api/clustering/start", json={"input_path": str(tmp_path)})

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to enqueue clustering job"


def test_pipeline_submit_returns_500_when_enqueue_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_app, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_clustering_runner", _RunnerStub())
    monkeypatch.setattr(db, "enqueue_job", lambda *args, **kwargs: (None, 0))

    body = {
        "input_path": str(tmp_path),
        "operations": ["cluster"],
        "clustering_threshold": 0.2,
    }
    with _build_client() as client:
        response = client.post("/api/pipeline/submit", json=body)

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to enqueue pipeline job for operation: cluster"


def test_pipeline_submit_requires_input_path(monkeypatch):
    monkeypatch.setattr(ui_app, "_check_rate_limit", lambda endpoint: None)

    with _build_client() as client:
        response = client.post("/api/pipeline/submit", json={"operations": ["score"]})

    assert response.status_code == 422


def test_outliers_endpoint_returns_detector_payload(monkeypatch):
    expected = {
        "outliers": [{
            "image_id": 5, 
            "file_path": "/photos/2024/img5.jpg",
            "outlier_score": 0.85,
            "z_score": -2.4,
            "nearest_neighbors": [
                {"image_id": 6, "file_path": "/photos/2024/img6.jpg", "similarity": 0.95}
            ]
        }],
        "stats": {
            "total_with_embeddings": 100,
            "folder_mean": 0.9,
            "folder_std": 0.05,
            "z_threshold": 1.8,
            "k_neighbors": 7,
            "outliers_found": 1
        },
        "skipped": [],
    }

    def fake_find_outliers(folder_path, z_threshold=None, k=None, limit=None):
        assert folder_path == "/photos/2024"
        assert z_threshold == 1.8
        assert k == 7
        assert limit == 33
        return expected

    from modules import similar_search
    monkeypatch.setattr(similar_search, "find_outliers", fake_find_outliers)

    with _build_client() as client:
        response = client.get(
            "/api/outliers",
            params={"folder_path": "/photos/2024", "z_threshold": 1.8, "k": 7, "limit": 33},
        )

    assert response.status_code == 200
    assert response.json() == expected


def test_outliers_endpoint_propagates_domain_error(monkeypatch):
    from modules import similar_search
    monkeypatch.setattr(similar_search, "find_outliers", lambda **kwargs: {"error": "folder_path is required"})

    with _build_client() as client:
        response = client.get("/api/outliers", params={"folder_path": "/bad/path"})

    assert response.status_code == 400
    assert response.json()["detail"] == "folder_path is required"


def test_outliers_endpoint_returns_500_on_unexpected_exception(monkeypatch):
    from modules import similar_search

    def _raise_unexpected(**kwargs):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(similar_search, "find_outliers", _raise_unexpected)

    with _build_client() as client:
        response = client.get("/api/outliers", params={"folder_path": "/bad/path"})

    assert response.status_code == 500
    assert response.json()["detail"] == "unexpected failure"
