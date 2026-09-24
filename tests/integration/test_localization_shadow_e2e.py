"""E2E: shadow localization persistence against real PostgreSQL (#387, AC-6..AC-16).

The decode/outcome logic is unit-tested in ``tests/test_localization_phase.py``; this
module covers what only a database shows: the atomic run+regions write, the single
current run per (image, detector), the ``localization`` phase status, and that nothing
outside the localization tables changes.

No model is loaded -- a fake detector returns fixed boxes. ``pytest.mark.postgres``.
"""

from __future__ import annotations

import json

import pytest
from PIL import Image

pytestmark = [pytest.mark.postgres]

from modules import db  # noqa: E402
from modules import localization as loc  # noqa: E402
from modules.bird_detection import rank_boxes  # noqa: E402

#: Tables the runner may write. Everything else must keep its row count.
_ALLOWED_TO_CHANGE = {
    "image_localization_runs", "image_regions", "image_phase_status",
    "jobs", "job_phases", "job_steps", "job_image_actions", "auditlog", "run_logs",
    # A ``failed`` phase status records an incident; asserted below to be localization's.
    "image_incidents",
}


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    # truncate_app_tables re-seeds pipeline_phases best-effort; seed through the app path
    # so the localization row and its enabled flag exist.
    db.seed_pipeline_phases()
    yield


class _FakeDetector:
    def __init__(self, boxes=None, error=None):
        self.boxes = boxes or []
        self.error = error

    def detect_boxes(self, image):
        if self.error:
            raise self.error
        return rank_boxes(self.boxes, *image.size, max_det=10)


def _ctx(detector, config_hash="cfg-a"):
    return loc.DetectorContext(enabled=True, detector=detector, version="test/v0", config_hash=config_hash)


@pytest.fixture
def image(tmp_path):
    """One image row whose file is a real 400x300 JPEG, with a legacy bird_bbox set."""
    path = tmp_path / "bird.jpg"
    Image.new("RGB", (400, 300), (40, 80, 120)).save(path)
    row = db.get_connector().execute_returning(
        "INSERT INTO images (file_path, bird_bbox) VALUES (?, ?::jsonb) RETURNING id",
        (str(path), json.dumps({"detected": False})),
    )
    return int(row[0]["id"]), str(path)


def _runs(image_id):
    return db.get_connector().query(
        "SELECT * FROM image_localization_runs WHERE image_id = ? ORDER BY id", (image_id,),
    )


def _regions(run_id):
    return db.get_connector().query(
        "SELECT * FROM image_regions WHERE localization_run_id = ? ORDER BY rank", (run_id,),
    )


_TWELVE_BOXES = [{"xyxy": (10 + i, 10, 60 + i, 70), "conf": 0.30 + i / 100} for i in range(12)]


def test_ac6_ac13_ac20_detected_run_with_ranked_regions(image):
    image_id, path = image
    out = loc.localize_image(image_id, path, _ctx(_FakeDetector(_TWELVE_BOXES)), max_regions=10, job_id=None)
    assert out.status == "detected"

    (run,) = _runs(image_id)
    assert run["status"] == "detected" and run["is_current"] is True
    regions = _regions(run["id"])
    assert len(regions) == 10
    assert [r["rank"] for r in regions] == list(range(10))
    confs = [r["confidence"] for r in regions]
    assert confs == sorted(confs, reverse=True)
    assert {r["object_class"] for r in regions} == {"bird"}

    # AC-13 provenance and AC-20 rendition identity.
    assert run["detector_version"] == "test/v0" and run["detector_config_hash"] == "cfg-a"
    assert run["source_hash"] and run["rendition_hash"]
    assert run["coord_space"] == "display_normalized"
    assert run["orientation"] == 1
    assert run["decode_route"] == "direct"
    assert (run["display_width"], run["display_height"]) == (400, 300)


def test_ac7_no_detection_has_no_regions(image):
    image_id, path = image
    loc.localize_image(image_id, path, _ctx(_FakeDetector([])), max_regions=10)
    (run,) = _runs(image_id)
    assert run["status"] == "no_detection"
    assert _regions(run["id"]) == []


def test_ac8_terminal_error_for_undecodable_source(image, tmp_path):
    image_id, _ = image
    bad = tmp_path / "private" / "broken.jpg"
    bad.parent.mkdir()
    bad.write_bytes(b"not a jpeg")
    loc.localize_image(image_id, str(bad), _ctx(_FakeDetector()), max_regions=10)
    (run,) = _runs(image_id)
    assert run["status"] == "terminal_error" and run["is_retryable"] is False
    assert "private" not in (run["error_detail"] or "")


def test_ac9_retryable_error_for_inference_failure(image):
    image_id, path = image
    loc.localize_image(image_id, path, _ctx(_FakeDetector(error=RuntimeError("boom"))), max_regions=10)
    (run,) = _runs(image_id)
    assert run["status"] == "retryable_error" and run["is_retryable"] is True


def test_ac10_disabled(image):
    image_id, path = image
    ctx = loc.DetectorContext(enabled=False, version="test/v0", config_hash="disabled-hash")
    loc.localize_image(image_id, path, ctx, max_regions=10)
    (run,) = _runs(image_id)
    assert run["status"] == "disabled"


def test_ac12_new_attempt_supersedes_the_current_one(image):
    image_id, path = image
    loc.localize_image(image_id, path, _ctx(_FakeDetector([]), "cfg-a"), max_regions=10)
    loc.localize_image(image_id, path, _ctx(_FakeDetector(_TWELVE_BOXES), "cfg-b"), max_regions=10)
    first, second = _runs(image_id)
    assert first["is_current"] is False and second["is_current"] is True
    assert second["detector_config_hash"] == "cfg-b"
    # History is immutable: the superseded attempt keeps its own outcome.
    assert first["status"] == "no_detection" and second["status"] == "detected"


def test_ac12_supersedes_a_legacy_import_row(image):
    """Stage 2 imports use the same detector key, so a shadow run replaces them as current."""
    image_id, path = image
    db.get_connector().execute(
        "INSERT INTO image_localization_runs (image_id, detector_key, detector_version, "
        "detector_config_hash, coord_space, status, is_current) "
        "VALUES (?, 'bird', 'legacy_unversioned', 'legacy_unversioned', 'legacy_unverified', "
        "'no_detection', TRUE)",
        (image_id,),
    )
    loc.localize_image(image_id, path, _ctx(_FakeDetector([])), max_regions=10)
    current = [r for r in _runs(image_id) if r["is_current"]]
    assert len(current) == 1 and current[0]["detector_version"] == "test/v0"


def test_ac14_unchanged_image_keeps_its_current_run(image):
    image_id, path = image
    detector = _FakeDetector([])
    loc.localize_image(image_id, path, _ctx(detector), max_regions=10)
    out = loc.localize_image(image_id, path, _ctx(detector), max_regions=10)
    assert out.unchanged is True
    assert len(_runs(image_id)) == 1


def _table_counts():
    conn = db.get_connector()
    tables = [r["table_name"] for r in conn.query(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )]
    return {t: int(conn.query_one(f'SELECT COUNT(*) AS c FROM "{t}"')["c"]) for t in tables}


def test_ac11_ac15_ac16_runner_batch(image, tmp_path, monkeypatch):
    from modules import localization_runner as lr

    image_id, path = image
    missing = db.get_connector().execute_returning(
        "INSERT INTO images (file_path) VALUES (?) RETURNING id", (str(tmp_path / "gone.jpg"),),
    )[0]["id"]
    failing_path = tmp_path / "second.jpg"
    Image.new("RGB", (200, 100)).save(failing_path)
    failing = db.get_connector().execute_returning(
        "INSERT INTO images (file_path) VALUES (?) RETURNING id", (str(failing_path),),
    )[0]["id"]
    # A consumer phase row that must survive untouched (AC-15).
    db.set_image_phase_status(image_id, "scoring", "done", executor_version="x")

    detector = _FakeDetector([{"xyxy": (10, 10, 60, 70), "conf": 0.8}])
    real_detect = detector.detect_boxes
    calls = {"n": 0}

    def _detect(img):
        calls["n"] += 1
        if calls["n"] == 2:  # second decodable image (``failing``) -> retryable
            raise RuntimeError("cuda error")
        return real_detect(img)

    detector.detect_boxes = _detect
    monkeypatch.setattr(lr, "load_detector_context", lambda _cfg: _ctx(detector))
    monkeypatch.setattr(lr, "localization_config", lambda: {})

    other_ips_sql = (
        "SELECT ips.image_id, pp.code, ips.status, ips.updated_at FROM image_phase_status ips "
        "JOIN pipeline_phases pp ON pp.id = ips.phase_id WHERE pp.code <> 'localization' "
        "ORDER BY ips.image_id, pp.code"
    )
    other_ips_before = db.get_connector().query(other_ips_sql)
    images_before = db.get_connector().query("SELECT * FROM images ORDER BY id")
    counts_before = _table_counts()
    job_id = db.create_job(str(tmp_path))

    lr.LocalizationRunner()._run_batch_internal(str(tmp_path), job_id, [image_id, missing, failing], None)

    # AC-11. Scoped to this test's images: the shared test database is not reliably
    # emptied between tests (truncate_app_tables' pipeline_phases re-seed aborts its
    # transaction), so other rows may exist.
    statuses = {
        r["image_id"]: r["status"] for r in db.get_connector().query(
            "SELECT ips.image_id, ips.status FROM image_phase_status ips "
            "JOIN pipeline_phases pp ON pp.id = ips.phase_id "
            "WHERE pp.code = 'localization' AND ips.image_id IN (?, ?, ?)",
            (image_id, missing, failing),
        )
    }
    assert statuses == {image_id: "done", missing: "skipped", failing: "failed"}

    # AC-15: images unchanged (bird_bbox included), consumer IPS untouched, and no table
    # outside the localization/job bookkeeping set changed size.
    assert db.get_connector().query("SELECT * FROM images ORDER BY id") == images_before
    assert db.get_connector().query(other_ips_sql) == other_ips_before
    counts_after = _table_counts()
    changed = {t for t in counts_after if counts_after[t] != counts_before.get(t)}
    assert changed <= _ALLOWED_TO_CHANGE, changed - _ALLOWED_TO_CHANGE
    incidents = db.get_connector().query(
        "SELECT pp.code FROM image_incidents ii LEFT JOIN pipeline_phases pp ON pp.id = ii.phase_id "
        "WHERE ii.image_id IN (?, ?, ?)",
        (image_id, missing, failing),
    )
    assert {r["code"] for r in incidents} <= {"localization"}

    # AC-16
    summary = db.get_job_report(job_id)["phases"]["localization"]
    assert summary["status_counts"] == {"detected": 1, "terminal_error": 1, "retryable_error": 1}
    assert summary["region_count_distribution"] == {"1": 1}
    assert summary["mean_decode_seconds"] is not None
    assert summary["mean_inference_seconds"] is not None
    assert "peak_gpu_memory_mib" in summary
    assert db.get_job(job_id)["status"] == "completed"
