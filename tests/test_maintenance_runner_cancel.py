"""Cancel must release the maintenance runner so queued runs can start."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.maintenance_runner import MaintenanceRunner  # noqa: E402


def test_cancelled_heal_does_not_mark_job_completed(monkeypatch):
    runner = MaintenanceRunner()
    statuses: list[str] = []

    monkeypatch.setattr("modules.maintenance_runner.db.get_job_phases", lambda job_id: [1])
    monkeypatch.setattr(
        "modules.maintenance_runner.db.update_job_status",
        lambda job_id, status, log=None: statuses.append(status),
    )
    monkeypatch.setattr("modules.maintenance_runner.db.set_job_phase_state", lambda *a, **k: None)
    monkeypatch.setattr("modules.maintenance_runner.db.update_job_progress", lambda *a, **k: None)
    monkeypatch.setattr("modules.maintenance_runner.db.update_job_log", lambda *a, **k: None)
    monkeypatch.setattr("modules.maintenance_runner.db.job_should_stop_processing", lambda job_id: False)
    monkeypatch.setattr(
        "modules.maintenance_runner.db.get_job",
        lambda job_id: {"id": job_id, "status": "cancelled"},
    )

    def _repair(*_a, **_k):
        runner.stop()
        return {"repaired": 0, "scanned": 0}

    monkeypatch.setattr("modules.thumbnail_maintenance.repair_thumbnail_paths_batch", _repair)
    monkeypatch.setattr(
        "modules.thumbnail_maintenance.regenerate_missing_thumbnails_batch",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("regen should not start after cancel")),
    )

    runner._run_job_internal(
        {
            "id": 6839,
            "input_path": "Tools: Heal Thumbnails",
            "queue_payload": '{"action":"heal_thumbnails","regen_limit":500}',
        }
    )

    assert statuses == ["running"]
    assert runner.is_running is False


def test_stop_runner_for_phase_stops_maintenance(monkeypatch):
    from modules.api import state

    class _Runner:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    runner = _Runner()
    monkeypatch.setattr(state, "_maintenance_runner", runner)
    assert state._stop_runner_for_phase("maintenance") is True
    assert runner.stopped is True
