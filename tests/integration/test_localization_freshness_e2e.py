"""Backend parity for selected-on-noncurrent-run cases from the skills authority study."""
import pytest

from modules import db
from modules.localization_legacy import read_bird_bbox, overlay_bird_bboxes
from modules.localization_selection import select_region
from tests.integration.test_localization_authority_e2e import image_run

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def _clean(postgres_test_session, clean_postgres):
    yield


def selected_image():
    conn = db.get_connector()
    iid, rid = image_run()
    conn.execute("UPDATE image_localization_runs SET display_width=100,display_height=100 WHERE id=?", (rid,))
    region = conn.query_one("SELECT id FROM image_regions WHERE localization_run_id=?", (rid,))["id"]
    selected = select_region(iid, region, "curated-test/1")
    assert selected["status"] == "selected"
    return iid, rid, selected


def test_noncurrent_selected_artifact_is_used_without_republishing_shadow():
    conn = db.get_connector()
    iid, rid, selected = selected_image()
    conn.execute("UPDATE image_localization_runs SET is_current=FALSE WHERE id=?", (rid,))
    conn.execute(
        "INSERT INTO image_localization_runs (image_id,detector_key,detector_version,detector_config_hash,"
        "source_hash,source_hash_version,rendition_hash,status,is_current,coord_space) "
        "VALUES (?,'bird','model','cfg','source','v1','rendition','no_detection',TRUE,'display_normalized')", (iid,),
    )
    conn.execute("UPDATE localization_authority_control SET selection_freshness_enabled=TRUE,mode='off' WHERE id=1")
    assert read_bird_bbox(conn, iid, prefer_normalized=False) == selected["bird_bbox"]
    rows = [{"id": iid, "bird_bbox": None}]
    overlay_bird_bboxes(rows, conn=conn, prefer_normalized=False)
    assert rows[0]["bird_bbox"] == selected["bird_bbox"]


def test_stale_projection_cannot_reappear_via_scalar_batch_or_view_fallback():
    conn = db.get_connector()
    iid, _, selected = selected_image()
    conn.execute("UPDATE localization_authority_control SET selection_freshness_enabled=TRUE WHERE id=1")
    conn.execute(
        "INSERT INTO localization_authority_observations (image_id,components) "
        "VALUES (?, '{\"source\":{\"status\":\"available\",\"hash\":\"changed\",\"version\":\"v1\"}}'::jsonb)", (iid,),
    )
    assert read_bird_bbox(conn, iid, prefer_normalized=False) is None
    assert read_bird_bbox(conn, iid, prefer_normalized=True) is None
    rows = [{"id": iid, "bird_bbox": selected["bird_bbox"]}]
    overlay_bird_bboxes(rows, conn=conn, prefer_normalized=False)
    assert rows[0]["bird_bbox"] is None
    assert conn.query_one("SELECT bird_bbox FROM image_bird_bbox_compat WHERE image_id=?", (iid,))["bird_bbox"] is None
    conn.execute("UPDATE localization_authority_control SET selection_freshness_enabled=FALSE WHERE id=1")
    assert read_bird_bbox(conn, iid, prefer_normalized=False) == selected["bird_bbox"]


def test_same_value_keyword_edit_records_new_external_ownership_event():
    conn = db.get_connector()
    iid, *_ = selected_image()
    first = conn.query_one("SELECT max(id) AS id FROM localization_change_journal WHERE image_id=?", (iid,))["id"]
    conn.execute("UPDATE image_keywords SET confidence=confidence WHERE image_id=?", (iid,))
    latest = conn.query_one("SELECT id,owner_context FROM localization_change_journal WHERE image_id=? ORDER BY id DESC LIMIT 1", (iid,))
    assert latest["id"] > first and latest["owner_context"] is None


def test_species_never_uses_stale_selected_crop_or_its_projected_fallback():
    from modules.bird_species import species_input_for_image, stored_box_input

    conn = db.get_connector()
    iid, rid, _ = selected_image()
    conn.execute("UPDATE localization_authority_control SET selection_freshness_enabled=TRUE WHERE id=1")
    conn.execute("UPDATE image_localization_runs SET source_hash='changed' WHERE id=?", (rid,))
    conn.execute(
        "INSERT INTO localization_authority_observations (image_id,components) "
        "VALUES (?, '{\"source\":{\"status\":\"available\",\"hash\":\"source\",\"version\":\"v1\"}}'::jsonb)", (iid,),
    )
    choice = species_input_for_image(iid)
    assert choice['mode'] == 'legacy' and choice['exclusion_reason'] == 'selection_stale'
    assert stored_box_input(iid,choice)['mode'] == 'full_frame'
