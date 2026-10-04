"""Localization repair lane (#527): gating, one job at a time, outage hold. No database.

Candidate SQL and the end-to-end enqueue are in
``tests/integration/test_localization_lane_e2e.py`` (``-m postgres``).
"""

from __future__ import annotations

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


def test_detector_outage_holds_the_lane_1m_then_5m_then_until_restart(fake_db, lane_on):
    fake_db.get_connector.return_value.query_one.return_value = {"n": 2}  # outage runs on the job
    t = 1000.0
    lane.maybe_enqueue(now=t)                       # job 101

    t += 61                                        # job 101 done with outage -> hold 60s
    assert lane.maybe_enqueue(now=t)["skipped"] == "detector_outage_hold"
    t += 61
    assert lane.maybe_enqueue(now=t)["enqueued"] == 102

    t += 61                                        # second outage -> hold 300s
    assert lane.maybe_enqueue(now=t)["skipped"] == "detector_outage_hold"
    t += 241
    assert lane.maybe_enqueue(now=t)["skipped"] == "detector_outage_hold"
    t += 61
    assert lane.maybe_enqueue(now=t)["enqueued"] == 103

    t += 61                                        # third outage -> hold until restart
    assert lane.maybe_enqueue(now=t)["skipped"] == "detector_outage_hold"
    assert lane.maybe_enqueue(now=t + 86_400)["skipped"] == "detector_outage_hold"
    lane.reset_state()                             # a restart clears it
    assert lane.maybe_enqueue(now=t + 86_500)["enqueued"] == 104


def test_a_clean_job_clears_the_outage_streak(fake_db, lane_on):
    fake_db.get_connector.return_value.query_one.return_value = {"n": 1}
    lane.maybe_enqueue(now=1000.0)
    lane.maybe_enqueue(now=1061.0)                 # outage noted, hold 60s
    fake_db.get_connector.return_value.query_one.return_value = {"n": 0}
    assert lane.maybe_enqueue(now=1122.0)["enqueued"] == 102
    lane.maybe_enqueue(now=1183.0)                 # clean job: streak reset
    assert lane.get_state()["outage_streak"] == 0


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
