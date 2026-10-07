"""Runs controls must respect delegated ownership at the API boundary."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.api.routers import electron_runs_lifecycle as lifecycle


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(lifecycle.create_electron_runs_lifecycle_router())
    with TestClient(app) as client:
        yield client


def test_pause_waiting_parent_uses_owned_child_control_only(client, monkeypatch):
    monkeypatch.setattr(lifecycle.db, "get_job", lambda jid: {"id": jid, "status": "running", "runner_state": "waiting_child"})
    update = Mock()
    stop = Mock()
    join = Mock()
    reconcile = Mock()
    monkeypatch.setattr(lifecycle.db, "update_job_status", update)
    monkeypatch.setattr(lifecycle, "_stop_runner_for_job_row", stop)
    monkeypatch.setattr(lifecycle, "_join_runner_threads", join)
    monkeypatch.setattr(lifecycle.db, "reconcile_stale_running_phases_for_jobs", reconcile)
    assert client.post("/runs/5/pause").status_code == 200
    update.assert_called_once_with(5, "paused", "user_pause")
    stop.assert_not_called()
    join.assert_not_called()
    reconcile.assert_not_called()


@pytest.mark.parametrize("action,method", [("skip", "set_job_phase_state"), ("retry", "force_reset_job_phase_to_queued")])
def test_manual_delegated_stage_control_returns_conflict(client, monkeypatch, action, method):
    monkeypatch.setattr(lifecycle.db, method, Mock(side_effect=ValueError("Invalid manual transition of delegated work")))
    response = client.post(f"/runs/5/stages/keywords/{action}")
    assert response.status_code == 409
    assert "delegated" in response.json()["detail"]


def test_force_waiting_parent_returns_conflict(client, monkeypatch):
    monkeypatch.setattr(lifecycle.db, "get_job", lambda jid: {"id": jid, "status": "running", "runner_state": "waiting_child"})
    response = client.post("/runs/5/force", json={"confirm": True})
    assert response.status_code == 409


def test_stage_read_preserves_delegated_child_id(client, monkeypatch):
    monkeypatch.setattr(lifecycle.db, "get_job", lambda jid: {"id": jid, "job_type": "selection"})
    monkeypatch.setattr(lifecycle.db, "get_job_phases", lambda jid: [{"phase_code": "keywords", "phase_order": 1, "state": "queued", "delegated_job_id": 6}])
    response = client.get("/runs/5/stages")
    assert response.status_code == 200
    assert response.json()[0]["delegated_job_id"] == 6


def test_job_detail_preserves_parent_and_phase_link_fields(monkeypatch):
    from modules import api, db

    monkeypatch.setattr(db, "get_job_by_id", lambda jid: {"id": jid, "status": "running", "parent_job_id": 4, "runner_state": "waiting_child"})
    monkeypatch.setattr(db, "get_job_phases", lambda jid: [{"phase_code": "keywords", "state": "queued", "delegated_job_id": 6}])
    app = FastAPI()
    app.include_router(api.create_api_router())
    with TestClient(app) as client:
        response = client.get("/api/jobs/5")
    assert response.status_code == 200
    assert response.json()["parent_job_id"] == 4
    assert response.json()["runner_state"] == "waiting_child"
    assert response.json()["phases"][0]["delegated_job_id"] == 6


def test_cancel_returns_conflict_if_delegated_chain_finishes_during_request(client, monkeypatch):
    monkeypatch.setattr(lifecycle.db, "get_job", lambda jid: {"id": jid, "status": "running", "runner_state": "waiting_child"})
    monkeypatch.setattr(lifecycle.db, "update_job_status", Mock(side_effect=ValueError("Delegated run #5: already_finished (completed)")))
    response = client.post("/runs/5/cancel")
    assert response.status_code == 409
    assert "already_finished" in response.json()["detail"]


def test_resume_returns_conflict_if_delegated_child_has_finished(client, monkeypatch):
    monkeypatch.setattr(lifecycle.db, "get_job", lambda jid: {"id": jid, "status": "paused", "queue_payload": "{}"})
    monkeypatch.setattr(lifecycle.db, "get_job_phases", lambda jid: [{"phase_code": "keywords"}])
    monkeypatch.setattr(lifecycle.db, "update_job_payload", Mock())
    monkeypatch.setattr(lifecycle.db, "requeue_job", Mock(side_effect=ValueError("Cannot resume delegated run #5: child_finished (completed); use a fresh retry")))
    response = client.post("/runs/5/resume")
    assert response.status_code == 409
    assert "fresh retry" in response.json()["detail"]
