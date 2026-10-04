"""E2E: localization repair lane candidates and enqueue on real PostgreSQL (#527).

Gating and the outage hold are unit-tested in ``tests/test_localization_lane.py``.
``pytest.mark.postgres``.
"""

from __future__ import annotations

import json

import pytest
from PIL import Image

pytestmark = [pytest.mark.postgres]

from modules import db  # noqa: E402
from modules import localization as loc  # noqa: E402
from modules import localization_lane as lane  # noqa: E402
from modules.job_dispatcher import JobDispatcher  # noqa: E402


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    db.seed_pipeline_phases()
    lane.reset_state()
    conn = db.get_connector()
    conn.execute("DELETE FROM localization_enablement")
    conn.execute(
        "INSERT INTO localization_enablement (detector_key, enabled_at) VALUES (?, '2026-01-01 00:00:00')",
        (loc.DETECTOR_KEY,),
    )
    yield
    lane.reset_state()


class _Failing:
    def detect_boxes(self, image):
        raise RuntimeError("cuda error")


def _image(tmp_path, name, created_at, *, metadata="done"):
    path = tmp_path / f"{name}.jpg"
    Image.new("RGB", (64, 48), (10, 20, 30)).save(path)
    image_id = int(db.get_connector().execute_returning(
        "INSERT INTO images (file_path, created_at) VALUES (?, ?) RETURNING id", (str(path), created_at),
    )[0]["id"])
    if metadata:
        db.set_image_phase_status(image_id, "metadata", metadata)
    return image_id, str(path)


def _fail(image_id, path, times, config_hash="cfg-a"):
    ctx = loc.DetectorContext(enabled=True, detector=_Failing(), version="test/v0", config_hash=config_hash)
    for _ in range(times):
        assert loc.localize_image(image_id, path, ctx, max_regions=10).status == "retryable_error"


def test_candidates_and_backlog(tmp_path):
    new_id, _ = _image(tmp_path, "new", "2026-02-01 00:00:00")
    _image(tmp_path, "new_no_metadata", "2026-02-01 00:00:00", metadata=None)
    _image(tmp_path, "legacy", "2025-06-01 00:00:00")
    ready_id, ready_path = _image(tmp_path, "ready", "2025-06-01 00:00:00")
    cooling_id, cooling_path = _image(tmp_path, "cooling", "2025-06-01 00:00:00")
    spent_id, spent_path = _image(tmp_path, "spent", "2025-06-01 00:00:00")
    _fail(ready_id, ready_path, 1)
    db.get_connector().execute(  # age the single failure past its one-minute wait
        "UPDATE image_localization_runs SET attempted_at = attempted_at - INTERVAL '2 minutes' WHERE image_id = ?",
        (ready_id,),
    )
    _fail(cooling_id, cooling_path, 1)
    _fail(spent_id, spent_path, 3)

    ids, backlog = lane.select_candidates()

    assert ids == [new_id, ready_id]
    assert backlog == {"new": 1, "retryable": 3, "cooling_down": 1, "exhausted": 1, "pending": 2}


def test_lane_enqueues_one_auto_selector_job(tmp_path, monkeypatch):
    new_id, _ = _image(tmp_path, "new", "2026-02-01 00:00:00")
    monkeypatch.setattr(lane, "lane_enabled", lambda: True)

    out = lane.maybe_enqueue(now=1000.0)
    job_id = out["enqueued"]
    assert job_id and out["backlog"]["new"] == 1

    job = db.get_job(job_id)
    payload = job["queue_payload"]
    payload = json.loads(payload) if isinstance(payload, str) else payload
    assert payload["localization_lane"] == "auto"
    assert JobDispatcher._explicit_stage_resolved_ids(payload, "localization") == [new_id]
    assert [p["phase_code"] for p in db.get_job_phases(job_id)] == ["localization"]

    # The queued lane job is itself core work in flight: no second job.
    assert lane.maybe_enqueue(now=1000.0 + lane.LANE_TICK_SEC + 1)["skipped"] == "lane_job_active"
