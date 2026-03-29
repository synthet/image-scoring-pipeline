"""
Jobs dequeued as ``running`` must reach a terminal status. Runners that return
early after ``update_job_status(..., "running")`` must mark the job ``failed``.
"""
import os
import shutil
import uuid

import pytest

from modules import db
from modules.indexing_runner import IndexingRunner
from modules.metadata_runner import MetadataRunner

pytestmark = [pytest.mark.db, pytest.mark.firebird]


def _tagging_runner_cls():
    """Lazy import so ``pytest -m 'not ml'`` never loads transformers/torch."""
    try:
        from modules.tagging import TaggingRunner

        return TaggingRunner
    except ImportError as e:  # pragma: no cover - optional ML stack
        pytest.skip(f"ML/tagging stack unavailable: {e}")


@pytest.fixture(scope="module")
def queue_db(tmp_path_factory):
    template = os.path.abspath("template.fdb")
    if not os.path.exists(template):
        pytest.skip("template.fdb not found - Firebird tests unavailable")

    tmp = tmp_path_factory.mktemp("runner_terminal")
    db_path = str(tmp / f"runner_terminal_{uuid.uuid4().hex}.fdb")
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
def clean_jobs(queue_db):
    conn = db.get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM job_phases")
    except Exception:
        pass
    c.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()


def test_indexing_empty_path_after_running_marks_failed(queue_db):
    job_id = db.create_job("D:/runner-fail/index", phase_code="indexing", job_type="indexing")
    IndexingRunner()._run_batch_internal("", job_id=job_id, skip_existing=True, resolved_image_ids=None)
    row = db.get_job(job_id)
    assert row is not None
    assert str(row.get("status") or "").lower() == "failed"


def test_indexing_missing_path_after_running_marks_failed(queue_db):
    job_id = db.create_job("D:/runner-fail/index2", phase_code="indexing", job_type="indexing")
    IndexingRunner()._run_batch_internal(
        "/nonexistent/path/runner_early_fail_99",
        job_id=job_id,
        skip_existing=True,
        resolved_image_ids=None,
    )
    row = db.get_job(job_id)
    assert str(row.get("status") or "").lower() == "failed"


def test_metadata_path_not_in_db_after_running_marks_failed(queue_db):
    job_id = db.create_job("D:/runner-fail/meta", phase_code="metadata", job_type="metadata")
    MetadataRunner()._run_batch_internal(
        "/no/such/image/runner_early_fail.jpg",
        job_id=job_id,
        skip_existing=True,
        resolved_image_ids=None,
    )
    row = db.get_job(job_id)
    assert str(row.get("status") or "").lower() == "failed"


@pytest.mark.ml
def test_tagging_model_load_failure_marks_job_failed(monkeypatch, queue_db, tmp_path):
    TaggingRunner = _tagging_runner_cls()
    class BoomKeywordScorer:
        def load_model(self):
            raise RuntimeError("simulated CLIP load failure")

    monkeypatch.setattr("modules.tagging.KeywordScorer", lambda *a, **k: BoomKeywordScorer())

    job_id = db.create_job("D:/runner-fail/tag", phase_code="keywords", job_type="tagging")
    folder = tmp_path / "empty_folder"
    folder.mkdir()
    TaggingRunner()._run_batch_internal(
        str(folder),
        job_id=job_id,
        overwrite=False,
        generate_captions=False,
        resolved_image_ids=None,
    )
    row = db.get_job(job_id)
    assert str(row.get("status") or "").lower() == "failed"


@pytest.mark.ml
def test_tagging_invalid_path_after_running_marks_failed(queue_db):
    """Path exists neither as dir nor as DB row — bypass real CLIP with a dummy scorer."""
    TaggingRunner = _tagging_runner_cls()
    job_id = db.create_job("D:/runner-fail/tag2", phase_code="keywords", job_type="tagging")

    class DummyScorer:
        def load_model(self):
            pass

        def predict(self, *args, **kwargs):
            return []

    runner = TaggingRunner()
    runner.scorer = DummyScorer()
    TaggingRunner._run_batch_internal(
        runner,
        "/not/a/dir/or/file/runner_early_fail",
        job_id=job_id,
        overwrite=False,
        generate_captions=False,
        resolved_image_ids=None,
    )
    row = db.get_job(job_id)
    assert str(row.get("status") or "").lower() == "failed"
