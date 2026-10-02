"""E2E: production localization selections and the bird_bbox projection (#484). ``pytest.mark.postgres``."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.postgres]

from modules import db  # noqa: E402
from modules.localization import write_run  # noqa: E402
from modules.localization_selection import (  # noqa: E402
    active_selection,
    revoke_selection,
    select_region,
)

SENTINEL = {"detected": False}
RULE = "v1_regate_rule/3:a1c2e1f64b24cc79"


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    yield


def _image(bbox=SENTINEL) -> int:
    import json
    import uuid

    row = db.get_connector().execute_returning(
        "INSERT INTO images (file_path, bird_bbox) VALUES (?, ?::jsonb) RETURNING id",
        (f"/tmp/sel-{uuid.uuid4().hex}.jpg", json.dumps(bbox) if bbox is not None else None))
    return int(row[0]["id"])


def _run(image_id: int, *, publish: bool, version: str = "v", boxes=((0.1, 0.2, 0.3, 0.4, 0.8),)) -> int:
    run = {"image_id": image_id, "detector_key": "bird", "detector_version": version,
           "detector_config_hash": "h", "coord_space": "display_normalized", "display_width": 1000,
           "display_height": 500, "status": "detected", "is_retryable": False, "is_current": publish}
    regions = [{"conf": c, "rank": i, "region": (x1, y1, x2, y2)} for i, (x1, y1, x2, y2, c) in enumerate(boxes)]
    return write_run(run, regions, publish=publish)


def _region(run_id: int, rank: int = 0) -> int:
    return int(db.get_connector().query_one(
        "SELECT id FROM image_regions WHERE localization_run_id = ? AND rank = ?", (run_id, rank))["id"])


def _bbox(image_id: int):
    return db.get_connector().query_one("SELECT bird_bbox FROM images WHERE id = ?", (image_id,))["bird_bbox"]


def test_unpublished_run_keeps_the_current_run():
    iid = _image()
    shadow = _run(iid, publish=True, version="shadow")
    _run(iid, publish=False, version="promoted")
    current = db.get_connector().query("SELECT id FROM image_localization_runs WHERE image_id = ? AND is_current",
                                       (iid,))
    assert [r["id"] for r in current] == [shadow]


def test_select_projects_bbox_and_revoke_restores_it():
    iid = _image()
    region = _region(_run(iid, publish=False))
    res = select_region(iid, region, RULE, {"stratum": "promote_large"}, expect_bird_bbox=SENTINEL)
    assert res["status"] == "selected"
    assert _bbox(iid) == {"x1": 100, "y1": 100, "x2": 300, "y2": 200, "conf": 0.8,
                          "img_w": 1000, "img_h": 500, "area_frac": 0.04}
    sel = active_selection(iid)
    assert sel["selected_by"] == RULE and sel["previous_bird_bbox"] == SENTINEL
    assert sel["evidence"] == {"stratum": "promote_large"}

    assert revoke_selection(iid, "test")["status"] == "revoked"
    assert _bbox(iid) == SENTINEL and active_selection(iid) is None


def test_select_refuses_changed_production_value():
    iid = _image({"x1": 1, "y1": 1, "x2": 5, "y2": 5, "conf": 0.5, "img_w": 10, "img_h": 10, "area_frac": 0.16})
    region = _region(_run(iid, publish=False))
    assert select_region(iid, region, RULE, expect_bird_bbox=SENTINEL)["status"] == "production_changed"
    assert active_selection(iid) is None


def test_one_active_selection_per_image():
    iid = _image()
    run = _run(iid, publish=False, boxes=((0.1, 0.1, 0.2, 0.2, 0.9), (0.5, 0.5, 0.6, 0.6, 0.7)))
    assert select_region(iid, _region(run, 0), RULE)["status"] == "selected"
    assert select_region(iid, _region(run, 0), RULE)["status"] == "already_selected"
    assert select_region(iid, _region(run, 1), RULE)["status"] == "other_selection_active"


def test_region_of_another_image_is_rejected():
    a, b = _image(), _image()
    region_b = _region(_run(b, publish=False))
    assert select_region(a, region_b, RULE)["status"] == "region_mismatch"


def test_revoke_keeps_a_bbox_changed_outside_the_selection():
    iid = _image()
    select_region(iid, _region(_run(iid, publish=False)), RULE)
    db.get_connector().execute("UPDATE images SET bird_bbox = '{\"detected\": false, \"error\": \"x\"}'::jsonb "
                               "WHERE id = ?", (iid,))
    assert revoke_selection(iid, "test")["status"] == "revoked_bbox_kept"
    assert _bbox(iid) == {"detected": False, "error": "x"} and active_selection(iid) is None


def test_selection_cascades_with_the_image():
    iid = _image()
    select_region(iid, _region(_run(iid, publish=False)), RULE)
    db.get_connector().execute("DELETE FROM images WHERE id = ?", (iid,))
    assert db.get_connector().query("SELECT id FROM image_localization_selections WHERE image_id = ?", (iid,)) == []


def test_promote_cli_dry_run_apply_rerun_and_revoke(tmp_path):
    """Manifest flow: only ready rows are promoted, re-apply is a no-op, revoke restores bird_bbox."""
    import json

    from scripts.maintenance import promote_localization_selections as cli

    ready, changed = _image(), _image({"x1": 1, "y1": 1, "x2": 2, "y2": 2, "conf": 0.5,
                                       "img_w": 10, "img_h": 10, "area_frac": 0.01})
    rows = []
    for iid in (ready, changed):
        v1 = _run(iid, publish=True, version="shadow-v1")
        rh = db.get_connector().query_one("SELECT rendition_hash FROM image_localization_runs WHERE id = ?",
                                          (v1,))["rendition_hash"]
        rows.append({"image_id": iid, "v1_run_id": v1, "rendition_hash": rh, "region": [0.5, 0.5, 0.7, 0.9],
                     "conf": 0.66, "source": "coco+refine:bird", "stratum": "promote_large"})
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"schema_version": 1, "selected_by": RULE, "detector_version": "v1_regate_rule/3",
                                "detector_config_hash": "a1c2e1f64b24cc79", "evidence": {"issue": 472},
                                "rows": rows}))
    manifest = cli.load_manifest(path)

    dry = cli.dry_run(manifest)
    assert dry["ready"] == 1 and dry["production_changed"] == 1
    assert cli.apply(manifest) == {"selected": 1, "skipped:production_changed": 1}
    assert _bbox(ready)["img_w"] == 1000 and _bbox(ready)["x1"] == 500
    sel = active_selection(ready)
    assert sel["evidence"] == {"issue": 472, "stratum": "promote_large", "source": "coco+refine:bird"}
    current = db.get_connector().query_one(
        "SELECT detector_version FROM image_localization_runs WHERE image_id = ? AND is_current", (ready,))
    assert current["detector_version"] == "shadow-v1"     # the shadow run stays current

    assert cli.apply(manifest)["skipped:already_selected"] == 1    # idempotent
    assert cli.revoke(manifest, "test") == {"revoked": 1, "not_ours": 1}
    assert _bbox(ready) == SENTINEL
