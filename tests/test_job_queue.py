import os
import shutil
import threading
import uuid

import pytest

from modules import db


@pytest.fixture(scope="module")
def queue_db(tmp_path_factory):
    template = os.path.abspath("template.fdb")
    if not os.path.exists(template):
        pytest.skip("template.fdb not found - Firebird tests unavailable")

    tmp = tmp_path_factory.mktemp("job_queue")
    db_path = str(tmp / f"job_queue_{uuid.uuid4().hex}.fdb")
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


def test_enqueue_job_returns_dense_positions_sequentially():
    positions = []
    for i in range(3):
        _, pos = db.enqueue_job(
            f"D:/queue-test/{i}",
            phase_code="scoring",
            job_type="scoring",
            queue_payload={"input_path": f"D:/queue-test/{i}"},
        )
        positions.append(pos)

    assert positions == [1, 2, 3]

    queued = db.get_queued_jobs(limit=10)
    assert [row["queue_position"] for row in queued] == [1, 2, 3]


def test_enqueue_job_concurrent_keeps_unique_stable_sort_keys():
    count = 8
    results = []
    errors = []
    lock = threading.Lock()
    gate = threading.Event()

    def worker(idx: int):
        gate.wait()
        try:
            job_id, pos = db.enqueue_job(
                f"D:/queue-concurrent/{idx}",
                phase_code="scoring",
                job_type="scoring",
                queue_payload={"idx": idx},
            )
            with lock:
                results.append((job_id, pos))
        except Exception as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    gate.set()
    for thread in threads:
        thread.join(timeout=5)

    assert not errors
    assert len(results) == count

    ids = [job_id for job_id, _ in results]
    assert len(set(ids)) == count

    conn = db.get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, queue_position
        FROM jobs
        WHERE status = 'queued'
        ORDER BY queue_position ASC
        """
    )
    rows = c.fetchall()
    conn.close()

    stored_positions = [int(row[1]) for row in rows]
    row_ids = [int(row[0]) for row in rows]
    assert len(set(stored_positions)) == count
    assert stored_positions == row_ids

    queued = db.get_queued_jobs(limit=50)
    assert [row["queue_position"] for row in queued] == list(range(1, count + 1))


def test_request_cancel_job_cancels_queued_without_reindex_updates():
    job1, _ = db.enqueue_job("D:/queue-cancel/1", phase_code="scoring", job_type="scoring")
    job2, _ = db.enqueue_job("D:/queue-cancel/2", phase_code="scoring", job_type="scoring")

    result = db.request_cancel_job(job1)
    assert result["success"] is True
    assert result["reason"] == "cancelled"

    cancelled = db.get_job_by_id(job1)
    assert cancelled["status"] == "cancelled"
    assert cancelled["queue_position"] is None

    queued = db.get_queued_jobs(limit=10)
    assert len(queued) == 1
    assert queued[0]["id"] == job2
    assert queued[0]["queue_position"] == 1


def test_request_cancel_job_running_not_supported():
    job_id, _ = db.enqueue_job("D:/queue-running/1", phase_code="scoring", job_type="scoring")
    running = db.dequeue_next_job()
    assert running and running["id"] == job_id

    result = db.request_cancel_job(job_id)
    assert result["success"] is False
    assert result["reason"] == "running_not_supported"

    row = db.get_job_by_id(job_id)
    assert row["status"] == "running"
    assert int(row.get("cancel_requested") or 0) == 0


def test_get_queued_jobs_limit_zero_returns_empty():
    db.enqueue_job("D:/queue-limit/1", phase_code="scoring", job_type="scoring")
    db.enqueue_job("D:/queue-limit/2", phase_code="scoring", job_type="scoring")

    assert db.get_queued_jobs(limit=0) == []
