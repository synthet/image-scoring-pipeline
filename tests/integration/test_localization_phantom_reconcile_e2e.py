"""E2E: phantom reconciliation of the ``localization`` phase (#527) on real PostgreSQL.

Orchestration is unit-tested in ``tests/test_phantom_phase_reconcile.py``; this module runs
the scan SQL against real run rows. ``pytest.mark.postgres``.
"""

from __future__ import annotations

import pytest
from PIL import Image

pytestmark = [pytest.mark.postgres]

from modules import db  # noqa: E402
from modules import localization as loc  # noqa: E402


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    db.seed_pipeline_phases()
    yield


class _Detector:
    def __init__(self, fail=False):
        self.fail = fail

    def detect_boxes(self, image):
        if self.fail:
            raise RuntimeError("cuda error")
        return []


def _image(tmp_path, name):
    folder_id = db.get_or_create_folder(str(tmp_path))
    path = tmp_path / f"{name}.jpg"
    Image.new("RGB", (64, 48), (10, 20, 30)).save(path)
    image_id = int(db.get_connector().execute_returning(
        "INSERT INTO images (file_path, folder_id) VALUES (?, ?) RETURNING id", (str(path), folder_id),
    )[0]["id"])
    return image_id, str(path)


def _localize(image_id, path, *, fail=False):
    ctx = loc.DetectorContext(enabled=True, detector=_Detector(fail), version="test/v0", config_hash="cfg-a")
    return loc.localize_image(image_id, path, ctx, max_regions=10, job_id=None).status


def _ips(image_id):
    row = db.get_connector().query_one(
        "SELECT ips.status FROM image_phase_status ips JOIN pipeline_phases pp ON pp.id = ips.phase_id "
        "WHERE pp.code = 'localization' AND ips.image_id = ?",
        (image_id,),
    )
    return (row or {}).get("status")


def test_reconciles_only_current_terminal_native_runs(tmp_path):
    finished, finished_path = _image(tmp_path, "finished")        # no IPS row, current no_detection
    lagging, lagging_path = _image(tmp_path, "lagging")           # IPS failed, current no_detection
    retrying, retrying_path = _image(tmp_path, "retrying")        # current retryable
    superseded, superseded_path = _image(tmp_path, "superseded")  # terminal run, then a retryable one
    imported, _ = _image(tmp_path, "imported")                    # legacy import row only

    assert _localize(finished, finished_path) == "no_detection"
    assert _localize(lagging, lagging_path) == "no_detection"
    db.set_image_phase_status(lagging, "localization", "failed", error="stale")
    assert _localize(retrying, retrying_path, fail=True) == "retryable_error"
    db.set_image_phase_status(retrying, "localization", "failed", error="cuda error")
    assert _localize(superseded, superseded_path) == "no_detection"
    # A new config hash bypasses AC-14 reuse, so the unchanged file gets a real retry.
    ctx_b = loc.DetectorContext(enabled=True, detector=_Detector(True), version="test/v0", config_hash="cfg-b")
    assert loc.localize_image(superseded, superseded_path, ctx_b, max_regions=10).status == "retryable_error"
    db.set_image_phase_status(superseded, "localization", "failed", error="cuda error")
    db.get_connector().execute(
        "INSERT INTO image_localization_runs (image_id, detector_key, detector_version, detector_config_hash, "
        "coord_space, status, is_current, legacy_payload) "
        "VALUES (?, 'bird', 'legacy_unversioned', 'legacy', 'legacy_unverified', 'no_detection', TRUE, "
        "'{\"detected\": false}'::jsonb)",
        (imported,),
    )

    dry = db.reconcile_phantom_complete_image_phases(("localization",), scope_path=str(tmp_path), dry_run=True)
    assert dry == {"localization": 2}
    assert _ips(finished) is None

    out = db.reconcile_phantom_complete_image_phases(("localization",), scope_path=str(tmp_path))

    assert out == {"localization": 2}
    assert _ips(finished) == "done"
    assert _ips(lagging) == "done"
    assert _ips(retrying) == "failed"
    assert _ips(superseded) == "failed"
    assert _ips(imported) is None
