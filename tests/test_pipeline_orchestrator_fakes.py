"""
Tier A: PipelineOrchestrator with fake runners and enable_background_tick=False.
"""
import os
import shutil
import time
import uuid

import pytest

pytestmark = pytest.mark.firebird

from modules import db
from modules.pipeline_orchestrator import PipelineOrchestrator
from tests.support.fake_runners import FakePhaseRunner


@pytest.fixture(scope="module")
def orch_db(tmp_path_factory):
    template = os.path.abspath("template.fdb")
    if not os.path.exists(template):
        pytest.skip("template.fdb not found - Firebird tests unavailable")

    tmp = tmp_path_factory.mktemp("orch_fakes")
    db_path = str(tmp / f"orch_{uuid.uuid4().hex}.fdb")
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
def clean_jobs(orch_db):
    conn = db.get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM job_phases")
    except Exception:
        pass
    c.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()


def _drain_orchestrator(orch: PipelineOrchestrator, max_ticks: int = 80):
    for _ in range(max_ticks):
        orch.on_tick()
        st = orch.get_status()
        if not st.get("active"):
            break
        time.sleep(0.02)


def test_orchestrator_single_indexing_phase_completes(orch_db):
    delay = 0.06
    indexing = FakePhaseRunner(delay_s=delay)
    metadata = FakePhaseRunner(delay_s=delay)
    scoring = FakePhaseRunner(delay_s=delay)
    tagging = FakePhaseRunner(delay_s=delay)
    selection = FakePhaseRunner(delay_s=delay)

    orch = PipelineOrchestrator(
        scoring_runner=scoring,
        tagging_runner=tagging,
        selection_runner=selection,
        indexing_runner=indexing,
        metadata_runner=metadata,
        enable_background_tick=False,
    )
    folder = "D:/orch_fake/single_idx"
    root_id = orch.start(folder, target_phases=["indexing"], force_rerun=True)
    assert root_id is not None
    assert orch.get_status()["active"] is True
    _drain_orchestrator(orch)
    assert orch.get_status()["active"] is False
    root = db.get_job_by_id(root_id)
    assert root["status"] == "completed"


def test_orchestrator_two_phases_sequence(orch_db):
    delay = 0.05
    f = lambda: FakePhaseRunner(delay_s=delay)
    indexing, metadata = f(), f()
    scoring, tagging, selection = f(), f(), f()
    orch = PipelineOrchestrator(
        scoring_runner=scoring,
        tagging_runner=tagging,
        selection_runner=selection,
        indexing_runner=indexing,
        metadata_runner=metadata,
        enable_background_tick=False,
    )
    folder = "D:/orch_fake/two"
    root_id = orch.start(folder, target_phases=["indexing", "metadata"], force_rerun=True)
    assert root_id is not None
    _drain_orchestrator(orch, max_ticks=120)
    assert orch.get_status()["active"] is False
    root = db.get_job_by_id(root_id)
    assert root["status"] == "completed"
    phases = db.get_job_phases(root_id) or []
    codes = [p.get("phase_code") for p in phases]
    assert "indexing" in codes and "metadata" in codes
    for p in phases:
        if p.get("phase_code") in ("indexing", "metadata"):
            assert p.get("state") == "completed"
