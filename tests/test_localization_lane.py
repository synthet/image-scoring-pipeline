"""Localization repair lane (#527): gating, one job at a time, outage hold. No database.

Candidate SQL and the end-to-end enqueue are in
``tests/integration/test_localization_lane_e2e.py`` (``-m postgres``).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from modules import localization_lane as lane
from modules.runs_autodrive_support import DEFAULT_TARGET_PHASES


@pytest.fixture(autouse=True)
def _fresh_lane():
    lane.reset_state()
    yield
    lane.reset_state()


@pytest.fixture
def fake_db(monkeypatch):
    db = MagicMock()
    db.get_queued_jobs_count.return_value = 0
    db.count_running_pipeline_jobs.return_value = 0
    db.get_jobs.return_value = []
    db.get_job.return_value = {"status": "completed"}
    db.get_connector.return_value.query_one.return_value = {"n": 0}
    for name in ("get_queued_jobs_count", "count_running_pipeline_jobs", "get_jobs", "get_job", "get_connector"):
        monkeypatch.setattr(f"modules.db.{name}", getattr(db, name), raising=False)
    return db


@pytest.fixture
def lane_on(monkeypatch):
    monkeypatch.setattr(lane, "lane_enabled", lambda: True)
    monkeypatch.setattr(lane, "select_candidates", lambda limit=lane.LANE_BATCH: ([1, 2], {"pending": 2}))
    enqueued = []

    def _enqueue(ids):
        enqueued.append(list(ids))
        return 100 + len(enqueued)

    monkeypatch.setattr(lane, "_enqueue", _enqueue)
    return enqueued


def test_localization_is_never_an_auto_drive_bucket():
    assert "localization" not in DEFAULT_TARGET_PHASES


def test_lane_is_off_by_default(monkeypatch):
    monkeypatch.setattr("modules.localization.localization_config", lambda: {})
    monkeypatch.setattr("modules.phases.is_phase_enabled", lambda code: True)
    assert lane.lane_enabled() is False
    assert lane.maybe_enqueue()["skipped"] == "disabled"


def test_lane_needs_both_the_phase_and_the_repair_flag(monkeypatch):
    monkeypatch.setattr("modules.localization.localization_config", lambda: {"repair": {"enabled": True}})
    monkeypatch.setattr("modules.phases.is_phase_enabled", lambda code: False)
    assert lane.lane_enabled() is False
    monkeypatch.setattr("modules.phases.is_phase_enabled", lambda code: True)
    assert lane.lane_enabled() is True


def test_admits_one_job_when_core_is_idle(fake_db, lane_on):
    out = lane.maybe_enqueue(now=1000.0)
    assert out["enqueued"] == 101 and lane_on == [[1, 2]]
    assert out["backlog"] == {"pending": 2}


@pytest.mark.parametrize("busy", ["queued", "running", "localization_job"])
def test_core_work_keeps_the_lane_out(fake_db, lane_on, busy):
    if busy == "queued":
        fake_db.get_queued_jobs_count.return_value = 1
    elif busy == "running":
        fake_db.count_running_pipeline_jobs.return_value = 1
    else:
        fake_db.get_jobs.return_value = [{"job_type": "localization", "status": "paused"}]
    assert lane.maybe_enqueue(now=1000.0)["skipped"] == "core_busy"
    assert lane_on == []


def test_never_a_second_job_while_the_first_is_active(fake_db, lane_on):
    lane.maybe_enqueue(now=1000.0)
    fake_db.get_job.return_value = {"status": "running"}
    assert lane.maybe_enqueue(now=1100.0)["skipped"] == "lane_job_active"
    assert len(lane_on) == 1


def test_tick_cooldown(fake_db, lane_on):
    lane.maybe_enqueue(now=1000.0)
    assert lane.maybe_enqueue(now=1000.0 + lane.LANE_TICK_SEC - 1)["skipped"] == "cooldown"


def test_detector_outage_holds_the_lane_1m_then_5m_capped_with_canaries(fake_db, lane_on):
    fake_db.get_connector.return_value.query_one.return_value = {"n": 2}  # outage runs on the job
    t = 1000.0
    lane.maybe_enqueue(now=t)                       # job 101, full batch
    assert lane_on[-1] == [1, 2]

    t += 61                                        # job 101 done with outage -> hold 60s
    assert lane.maybe_enqueue(now=t)["skipped"] == "detector_outage_hold"
    t += 61
    assert lane.maybe_enqueue(now=t)["enqueued"] == 102
    assert lane_on[-1] == [1]                      # one-image canary while the streak lasts

    t += 61                                        # second outage -> hold 300s
    assert lane.maybe_enqueue(now=t)["skipped"] == "detector_outage_hold"
    t += 241
    assert lane.maybe_enqueue(now=t)["skipped"] == "detector_outage_hold"
    t += 61
    assert lane.maybe_enqueue(now=t)["enqueued"] == 103

    t += 61                                        # third outage -> still capped at 300s, never parked
    assert lane.maybe_enqueue(now=t)["skipped"] == "detector_outage_hold"
    t += 241
    assert lane.maybe_enqueue(now=t)["skipped"] == "detector_outage_hold"
    t += 61
    assert lane.maybe_enqueue(now=t)["enqueued"] == 104
    assert lane_on[-1] == [1]


def test_recovered_canary_resumes_full_batches_without_restart(fake_db, lane_on):
    fake_db.get_connector.return_value.query_one.return_value = {"n": 1}
    t = 1000.0
    for _ in range(6):                             # three outage jobs, each followed by its hold
        lane.maybe_enqueue(now=t)
        t += 400
    assert lane.get_state()["outage_streak"] == 3
    fake_db.get_connector.return_value.query_one.return_value = {"n": 0}  # detector recovers
    assert lane.maybe_enqueue(now=t)["enqueued"] is not None and lane_on[-1] == [1]
    t += 61                                        # clean canary resets the streak
    assert lane.maybe_enqueue(now=t)["enqueued"] is not None
    assert lane_on[-1] == [1, 2] and lane.get_state()["outage_streak"] == 0


def test_a_clean_job_clears_the_outage_streak(fake_db, lane_on):
    fake_db.get_connector.return_value.query_one.return_value = {"n": 1}
    lane.maybe_enqueue(now=1000.0)
    lane.maybe_enqueue(now=1061.0)                 # outage noted, hold 60s
    fake_db.get_connector.return_value.query_one.return_value = {"n": 0}
    assert lane.maybe_enqueue(now=1122.0)["enqueued"] == 102
    lane.maybe_enqueue(now=1183.0)                 # clean job: streak reset
    assert lane.get_state()["outage_streak"] == 0


def test_held_lane_is_visible_through_status_and_diagnostics(fake_db, lane_on, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from modules import runs_autodrive as drive
    from modules.api.routers.electron_runs_plan import create_electron_runs_plan_router

    fake_db.get_connector.return_value.query_one.return_value = {"n": 1}
    for now in (1000.0, 1061.0, 1122.0, 1183.0, 1544.0, 1605.0):
        lane.maybe_enqueue(now=now)
    before = lane.get_state()
    monkeypatch.setattr(lane, "time", SimpleNamespace(time=lambda: 1605.0))  # status reads the clock
    core_state = {"enabled": True, "last_result": {"total_outstanding": 1,
                  "bucket_counts": {"awaiting_scoring": 1}, "health": {"schedulable_folders": 1}}}
    monkeypatch.setattr(drive, "get_drive_state", lambda: core_state)
    monkeypatch.setattr(drive, "_recent_auto_drive_jobs", lambda **kw: [])
    app = FastAPI()
    app.include_router(create_electron_runs_plan_router(), prefix="/api")
    with TestClient(app) as client:
        response = client.get("/api/runs/drive/status")
    assert response.status_code == 200
    status = response.json()
    assert status["localization_lane"]["hold_reason"] == "detector_outage_hold"
    assert status["localization_lane"]["restart_required"] is False
    assert status["localization_lane"]["hold_until"] == 1905.0
    assert status["localization_lane"]["hold_seconds_remaining"] == 300.0
    assert status["localization_lane"]["canary_pending"] is True
    assert status["state"] == core_state and status["outstanding"]["total_outstanding"] == 1
    diagnostics = drive.get_drive_diagnostics()
    assert any(row["code"] == "detector_outage_hold" and row["scope"] == "localization_lane"
               for row in diagnostics["anomalies"])
    json.dumps(diagnostics, allow_nan=False)
    from modules.mcp.tools import jobs as mcp_jobs

    mcp_diagnostics = mcp_jobs.get_drive_diagnostics()
    assert mcp_diagnostics["status"]["localization_lane"] == status["localization_lane"]
    json.dumps(mcp_diagnostics, allow_nan=False)
    assert lane.get_state() == before and len(lane_on) == 3


@pytest.mark.parametrize("now,remaining,reason", [
    (1061.0, 60.0, "detector_outage_hold"),
    (1120.0, 1.0, "detector_outage_hold"),
    (1121.0, 0.0, None),
    (1122.0, 0.0, None),
])
def test_diagnostics_describe_backoff_without_advancing_lane(fake_db, lane_on, now, remaining, reason):
    fake_db.get_connector.return_value.query_one.return_value = {"n": 1}
    lane.maybe_enqueue(now=1000.0)
    lane.maybe_enqueue(now=1061.0)
    before = lane.get_state()
    status = lane.get_diagnostic_state(now=now)
    assert status["hold_until"] == 1121.0
    assert status["hold_seconds_remaining"] == remaining
    assert status["hold_reason"] == reason
    assert status["restart_required"] is False
    json.dumps(status, allow_nan=False)
    status["backlog"]["pending"] = 999
    assert lane.get_state() == before and len(lane_on) == 1


def test_no_outage_has_no_diagnostic_hold(monkeypatch):
    candidates = MagicMock(side_effect=AssertionError("diagnostics must not scan candidates"))
    monkeypatch.setattr(lane, "select_candidates", candidates)
    status = lane.get_diagnostic_state(now=1000.0)
    assert status["hold_reason"] is None and status["restart_required"] is False
    assert status["hold_seconds_remaining"] == 0.0
    assert status["source"] == "process_local"
    candidates.assert_not_called()


def test_lane_errors_never_escape(monkeypatch):
    monkeypatch.setattr(lane, "lane_enabled", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert lane.maybe_enqueue()["skipped"] == "error"


def test_dispatcher_idle_tick_runs_drive_then_lane(monkeypatch):
    from modules.job_dispatcher import JobDispatcher

    calls = []
    monkeypatch.setattr("modules.runs_autodrive.drive_tick", lambda: calls.append("drive"))
    monkeypatch.setattr(lane, "maybe_enqueue", lambda: calls.append("lane") or (_ for _ in ()).throw(RuntimeError()))
    d = JobDispatcher.__new__(JobDispatcher)
    d._maybe_drive_tick()
    d._maybe_localization_lane()  # a lane failure is swallowed
    assert calls == ["drive", "lane"]
