"""ScoringRunner with MockScoringEngine + MockLiqeScorer (empty folder, no GPU)."""

from __future__ import annotations

import os
import shutil
import time
import uuid
from unittest.mock import patch

import pytest

from modules import db
from modules.engines.base import IScoringEngine
from modules.engines.mock import MockLiqeScorer, MockScoringEngine
from modules.scoring import ScoringRunner


def test_mock_scoring_engine_isinstance_iscoring_engine():
    assert isinstance(MockScoringEngine(), IScoringEngine)


@pytest.fixture(scope="module")
def scoring_mock_db(tmp_path_factory):
    template = os.path.abspath("template.fdb")
    if not os.path.exists(template):
        pytest.skip("template.fdb not found - Firebird tests unavailable")

    tmp = tmp_path_factory.mktemp("scoring_mock")
    db_path = str(tmp / f"score_mock_{uuid.uuid4().hex}.fdb")
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


@pytest.mark.firebird
@patch("modules.scoring.db.backup_database", lambda *args, **kwargs: None)
def test_scoring_runner_mock_engines_empty_folder_completes(scoring_mock_db, tmp_path):
    folder = tmp_path / "empty_score"
    folder.mkdir()

    job_id = db.create_job(str(folder), job_type="scoring", status="pending")

    runner = ScoringRunner(scoring_engine=MockScoringEngine(), liqe_scorer=MockLiqeScorer())
    assert runner.start_batch(str(folder), job_id, skip_existing=False) == "Started"
    deadline = time.time() + 30.0
    while time.time() < deadline and runner.is_running:
        time.sleep(0.05)

    assert not runner.is_running
    row = db.get_job_by_id(job_id)
    assert row["status"] == "completed"
