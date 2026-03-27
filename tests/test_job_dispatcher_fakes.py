"""
Tier A: JobDispatcher with fake runners (no ML).

Requires Firebird + template.fdb (same as test_job_queue).
"""
import os
import shutil
import time
import uuid

import pytest

pytestmark = pytest.mark.firebird

from modules import db
from modules.job_dispatcher import JobDispatcher
from tests.support.fake_runners import FakeScoringRunner, FakeTaggingRunner


@pytest.fixture(scope="module")
def dispatcher_db(tmp_path_factory):
    template = os.path.abspath("template.fdb")
    if not os.path.exists(template):
        pytest.skip("template.fdb not found - Firebird tests unavailable")

    tmp = tmp_path_factory.mktemp("job_dispatcher_fakes")
    db_path = str(tmp / f"dispatcher_{uuid.uuid4().hex}.fdb")
    shutil.copy2(template, db_path)

    original_path = db.DB_PATH
    db.DB_PATH = os.path.abspath(db_path)
    db.reset_init_db_state_for_tests()
    try:
        db.init_db()
    except Exception as exc:
        db.DB_PATH = original_path
        pytest.skip(f"DB init failed: {exc}")

    yield
    db.DB_PATH = original_path


@pytest.fixture(autouse=True)
def clean_jobs(dispatcher_db):
    conn = db.get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM job_phases")
    except Exception:
        pass
    c.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()


def test_dispatcher_tick_starts_scoring_job_and_completes(dispatcher_db):
    fake = FakeScoringRunner(delay_s=0.05)
    d = JobDispatcher(scoring_runner=fake, poll_interval=5.0)
    job_id, _ = db.enqueue_job(
        "D:/disp-fake/1",
        phase_code="scoring",
        job_type="scoring",
        queue_payload={"input_path": "D:/disp-fake/1"},
    )
    d.tick_for_tests()
    row = db.get_job_by_id(job_id)
    assert row["status"] == "running"
    for _ in range(50):
        if not fake.is_running and db.get_job_by_id(job_id)["status"] != "running":
            break
        time.sleep(0.02)
    assert db.get_job_by_id(job_id)["status"] == "completed"


def test_dispatcher_serializes_two_jobs(dispatcher_db):
    fake = FakeScoringRunner(delay_s=0.04)
    d = JobDispatcher(scoring_runner=fake, poll_interval=5.0)
    j1, _ = db.enqueue_job(
        "D:/disp-fake/a",
        phase_code="scoring",
        job_type="scoring",
        queue_payload={"input_path": "D:/disp-fake/a"},
    )
    j2, _ = db.enqueue_job(
        "D:/disp-fake/b",
        phase_code="scoring",
        job_type="scoring",
        queue_payload={"input_path": "D:/disp-fake/b"},
    )
    d.tick_for_tests()
    assert db.get_job_by_id(j1)["status"] == "running"
    assert db.get_job_by_id(j2)["status"] == "queued"
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if db.get_job_by_id(j1)["status"] == "completed":
            break
        time.sleep(0.03)
    assert db.get_job_by_id(j1)["status"] == "completed"
    d.tick_for_tests()
    assert db.get_job_by_id(j2)["status"] == "running"
    while time.time() < deadline:
        if db.get_job_by_id(j2)["status"] == "completed":
            break
        time.sleep(0.03)
    assert db.get_job_by_id(j2)["status"] == "completed"


def test_dispatcher_tagging_job_with_fake_runner(dispatcher_db):
    fake = FakeTaggingRunner(delay_s=0.05)
    d = JobDispatcher(tagging_runner=fake, poll_interval=5.0)
    job_id, _ = db.enqueue_job(
        "D:/disp-tag/1",
        phase_code="keywords",
        job_type="tagging",
        queue_payload={"input_path": "D:/disp-tag/1"},
    )
    d.tick_for_tests()
    for _ in range(50):
        if db.get_job_by_id(job_id)["status"] == "completed":
            break
        time.sleep(0.02)
    assert db.get_job_by_id(job_id)["status"] == "completed"


def test_dispatcher_marks_failed_when_runner_returns_error(dispatcher_db):
    class BadRunner:
        is_running = False

        def get_status(self):
            return False, "", "Idle", 0, 0

        def start_batch(self, *args, **kwargs):
            return "Error: nope"

    d = JobDispatcher(scoring_runner=BadRunner(), poll_interval=5.0)
    job_id, _ = db.enqueue_job(
        "D:/disp-bad/1",
        phase_code="scoring",
        job_type="scoring",
        queue_payload={"input_path": "D:/disp-bad/1"},
    )
    d.tick_for_tests()
    row = db.get_job_by_id(job_id)
    assert row["status"] == "failed"
