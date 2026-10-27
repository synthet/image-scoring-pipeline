"""E2E: bounded localization repair against real run history (#527).

The attempt/backoff rules are unit-tested in ``tests/test_localization_policy.py``; this
module checks the history query and the runner against PostgreSQL. No model is loaded --
a fake detector fails on demand. ``pytest.mark.postgres``.
"""

from __future__ import annotations

import pytest
from PIL import Image

pytestmark = [pytest.mark.postgres]

from modules import db  # noqa: E402
from modules import localization as loc  # noqa: E402
from modules import localization_policy as policy  # noqa: E402
from modules import localization_runner as lr  # noqa: E402


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    db.seed_pipeline_phases()
    yield


class _Detector:
    def __init__(self):
        self.calls = 0
        self.fail = True

    def detect_boxes(self, image):
        self.calls += 1
        if self.fail:
            raise RuntimeError("cuda error")
        return []


@pytest.fixture
def setup(tmp_path, monkeypatch):
    path = tmp_path / "bird.jpg"
    Image.new("RGB", (64, 48), (10, 20, 30)).save(path)
    image_id = int(db.get_connector().execute_returning(
        "INSERT INTO images (file_path) VALUES (?) RETURNING id", (str(path),),
    )[0]["id"])
    detector = _Detector()
    ctx = loc.DetectorContext(enabled=True, detector=detector, version="test/v0", config_hash="cfg-a")
    monkeypatch.setattr(lr, "load_detector_context", lambda _cfg: ctx)
    monkeypatch.setattr(lr, "localization_config", lambda: {})
    monkeypatch.setattr(lr, "scene_route_settings", lambda: {"enabled": False})
    return image_id, detector, str(tmp_path)


def _batch(image_id, scope, *, repair_limited):
    job_id = db.create_job(scope)
    lr.LocalizationRunner()._run_batch_internal(scope, job_id, [image_id], None, repair_limited=repair_limited)
    return job_id


def _summary(job_id):
    return db.get_job_report(job_id)["phases"]["localization"]


def test_successful_retry_reenters_running_under_strict_phase_transitions(setup, monkeypatch):
    from modules import config

    image_id, detector, scope = setup
    get_config_value = config.get_config_value

    def strict_config(key, *args, **kwargs):
        if key == "database.strict_phase_transitions":
            return True
        return get_config_value(key, *args, **kwargs)

    monkeypatch.setattr(config, "get_config_value", strict_config)

    first = _batch(image_id, scope, repair_limited=False)
    assert _summary(first)["status_counts"] == {"retryable_error": 1}
    detector.fail = False

    retried = _batch(image_id, scope, repair_limited=False)

    assert db.get_job(retried)["status"] == "completed"
    assert loc.get_current_run(image_id)["status"] == "no_detection"
    phase = db.get_connector().query_one(
        "SELECT s.status,s.started_at,s.finished_at FROM image_phase_status s "
        "JOIN pipeline_phases p ON p.id=s.phase_id WHERE s.image_id=? AND p.code='localization'",
        (image_id,),
    )
    assert phase["status"] == "done"
    assert phase["started_at"] <= phase["finished_at"]


def test_history_query_reads_newest_first_with_db_age(setup):
    image_id, _, scope = setup
    for _ in range(2):
        _batch(image_id, scope, repair_limited=False)

    history = policy.fetch_run_history([image_id])[image_id]
    assert [r["status"] for r in history] == ["retryable_error", "retryable_error"]
    assert all(r["source_hash"] for r in history)
    assert all(float(r["age_seconds"]) >= 0 for r in history)
    assert policy.repair_state(history).attempts == 2


def test_failure_cools_down_then_exhausts_and_job_stays_completed(setup, monkeypatch):
    image_id, detector, scope = setup

    first = _batch(image_id, scope, repair_limited=False)
    # S4-4: retryable per-image failures leave the job completed, listed in the summary.
    assert db.get_job(first)["status"] == "completed"
    assert _summary(first)["status_counts"] == {"retryable_error": 1}
    phase_sql = (
        "SELECT s.* FROM image_phase_status s JOIN pipeline_phases p ON p.id=s.phase_id "
        "WHERE s.image_id=? AND p.code='localization'"
    )
    phase_before_cooling = db.get_connector().query_one(phase_sql, (image_id,))

    # Inside the one-minute backoff the auto lane leaves the image alone.
    cooling = _batch(image_id, scope, repair_limited=True)
    assert detector.calls == 1
    assert _summary(cooling)["repair_deferred"] == {"cooling_down": 1}
    assert db.get_connector().query_one(phase_sql, (image_id,)) == phase_before_cooling

    for _ in range(2):  # explicit submits are the retry: no limit
        _batch(image_id, scope, repair_limited=False)
    assert detector.calls == 3

    phase_before_exhaustion = db.get_connector().query_one(phase_sql, (image_id,))
    exhausted = _batch(image_id, scope, repair_limited=True)
    assert detector.calls == 3
    assert _summary(exhausted)["repair_deferred"] == {"exhausted": 1}
    assert db.get_job(exhausted)["status"] == "completed"
    assert db.get_connector().query_one(phase_sql, (image_id,)) == phase_before_exhaustion

    # A new detector configuration is a new artifact identity: the lane may try again.
    monkeypatch.setattr(lr, "load_detector_context", lambda _cfg: loc.DetectorContext(
        enabled=True, detector=detector, version="test/v1", config_hash="cfg-b"))
    detector.fail = False
    _batch(image_id, scope, repair_limited=True)
    assert detector.calls == 4
    assert loc.get_current_run(image_id)["status"] == "no_detection"
