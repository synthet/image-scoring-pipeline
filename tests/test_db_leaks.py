"""
Connection hygiene for high-churn DB helpers (e.g. set_image_phase_status guard path).

Run: pytest tests/test_db_leaks.py -v -m "db and firebird"
"""
import os
import shutil
import uuid

import pytest

from modules import db
from modules.phases import PhaseCode, PhaseStatus

pytestmark = [pytest.mark.db, pytest.mark.firebird]


@pytest.fixture(scope="module")
def leak_db(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("db_leaks")
    db_path = str(tmp / f"leaks_{uuid.uuid4().hex}.fdb")
    template = os.path.abspath("template.fdb")
    if not os.path.exists(template):
        pytest.skip("template.fdb not found — Firebird not available")
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


def _add_test_image(filename="leak_guard.jpg"):
    conn = db.get_db()
    c = conn.cursor()
    path = f"leak_test_folder/{filename}"
    c.execute(
        "INSERT INTO images (file_path, folder_id, file_name) "
        "VALUES (?, (SELECT FIRST 1 id FROM folders), ?) RETURNING id",
        (path, filename),
    )
    row = c.fetchone()
    conn.commit()
    conn.close()
    return row[0] if row else None


def test_set_image_phase_status_guard_loop_still_allows_queries(leak_db):
    """Many running→running no-ops must not exhaust connections."""
    img_id = _add_test_image()
    if img_id is None:
        pytest.skip("Could not insert test image")

    db.set_image_phase_status(img_id, PhaseCode.METADATA, PhaseStatus.RUNNING)
    for _ in range(200):
        db.set_image_phase_status(img_id, PhaseCode.METADATA, PhaseStatus.RUNNING)

    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM images WHERE id = ?", (img_id,))
    n = c.fetchone()[0]
    conn.close()
    assert n == 1
