"""E2E: localization enablement boundary, new-images-only scope, claim reuse (#527).

Unit coverage of the filter rules is in ``tests/test_localization_policy.py``; this module
checks the SQL against real PostgreSQL. No model is loaded. ``pytest.mark.postgres``.
"""

from __future__ import annotations

import pytest
from PIL import Image

pytestmark = [pytest.mark.postgres]

from modules import db  # noqa: E402
from modules import localization as loc  # noqa: E402
from modules import localization_policy as policy  # noqa: E402
from modules.job_dispatcher import JobDispatcher  # noqa: E402

_BOUNDARY = "2026-01-01 00:00:00"


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    db.seed_pipeline_phases()
    yield


def _set_boundary(ts=_BOUNDARY):
    conn = db.get_connector()
    conn.execute("DELETE FROM localization_enablement")
    conn.execute(
        "INSERT INTO localization_enablement (detector_key, enabled_at) VALUES (?, ?)",
        (loc.DETECTOR_KEY, ts),
    )


def _image(tmp_path, name, created_at):
    path = tmp_path / f"{name}.jpg"
    Image.new("RGB", (64, 48), (10, 20, 30)).save(path)
    row = db.get_connector().execute_returning(
        "INSERT INTO images (file_path, created_at) VALUES (?, ?) RETURNING id",
        (str(path), created_at),
    )
    return int(row[0]["id"]), path


class _NoBirds:
    def detect_boxes(self, image):
        return []


def _localize(image_id, path):
    ctx = loc.DetectorContext(enabled=True, detector=_NoBirds(), version="test/v0", config_hash="cfg-a")
    return loc.localize_image(image_id, str(path), ctx, max_regions=10, job_id=None)


def test_boundary_is_written_once_and_kept():
    db.get_connector().execute("DELETE FROM localization_enablement")
    first = policy.ensure_enablement_boundary()
    second = policy.ensure_enablement_boundary()

    assert first is not None and first == second
    rows = db.get_connector().query("SELECT * FROM localization_enablement")
    assert len(rows) == 1 and rows[0]["detector_key"] == loc.DETECTOR_KEY


def test_new_images_only_scope(tmp_path):
    _set_boundary()
    new_id, _ = _image(tmp_path, "new", "2026-02-01 00:00:00")
    legacy_id, _ = _image(tmp_path, "legacy", "2025-06-01 00:00:00")
    unchanged_id, unchanged_path = _image(tmp_path, "unchanged", "2025-06-01 00:00:00")
    changed_id, changed_path = _image(tmp_path, "changed", "2025-06-01 00:00:00")
    assert _localize(unchanged_id, unchanged_path).status == "no_detection"
    assert _localize(changed_id, changed_path).status == "no_detection"
    Image.new("RGB", (80, 60), (200, 10, 10)).save(changed_path)  # new size and bytes

    kept = policy.filter_auto_eligible([legacy_id, unchanged_id, changed_id, new_id])

    assert kept == [changed_id, new_id]


def test_two_submissions_share_one_open_claim(tmp_path):
    image_id, _ = _image(tmp_path, "claimed", "2026-02-01 00:00:00")
    job_a = db.create_job("SELECTOR_LOCALIZATION_A")
    job_b = db.create_job("SELECTOR_LOCALIZATION_B")

    assert JobDispatcher._claim_explicit_ids(job_a, "localization", [image_id]) == [image_id]
    assert JobDispatcher._claim_explicit_ids(job_b, "localization", [image_id]) == []

    open_claims = db.get_connector().query(
        "SELECT job_id FROM image_phase_work_claims "
        "WHERE image_id = ? AND phase_code = 'localization' AND status IN ('queued', 'running')",
        (image_id,),
    )
    assert [int(r["job_id"]) for r in open_claims] == [job_a]
