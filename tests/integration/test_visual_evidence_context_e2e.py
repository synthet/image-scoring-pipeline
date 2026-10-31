"""Diagnostics describe the authoritative bird region, not the newest run (#714)."""
import pytest
from PIL import Image

from modules import db
from modules import localization as loc
from modules.bird_detection import rank_boxes
from modules.localization_selection import revoke_selection, select_region
from modules.visual_evidence.context import load_context

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def _clean(postgres_test_session, clean_postgres):
    yield


class _Boxes:
    def __init__(self, *boxes):
        self.boxes = [{"xyxy": list(b), "conf": 0.9} for b in boxes]

    def detect_boxes(self, image):
        return rank_boxes(self.boxes, *image.size, max_det=10)


def _ctx(boxes, config_hash):
    return loc.DetectorContext(enabled=True, detector=_Boxes(*boxes), version="test/v0", config_hash=config_hash)


def _image(tmp_path):
    path = tmp_path / "bird.png"
    Image.new("RGB", (200, 100), (40, 80, 120)).save(path)
    iid = db.get_connector().execute_returning("INSERT INTO images (file_path) VALUES (?) RETURNING id", (str(path),))[0]["id"]
    return int(iid), str(path)


def _rank0(iid):
    return db.get_connector().query_one(
        "SELECT g.id FROM image_regions g JOIN image_localization_runs r ON r.id=g.localization_run_id "
        "WHERE r.image_id=? AND r.is_current AND g.rank=0", (iid,))["id"]


def test_selected_region_wins_over_a_newer_shadow_run(tmp_path):
    iid, path = _image(tmp_path)
    assert loc.localize_image(iid, path, _ctx([(20, 10, 100, 60)], "cfg-selected"), max_regions=10).status == "detected"
    assert select_region(iid, _rank0(iid), "test")["status"] == "selected"
    assert loc.localize_image(iid, path, _ctx([(120, 40, 190, 95)], "cfg-shadow"), max_regions=10).status == "detected"
    context = load_context(iid)
    assert context["region"] == pytest.approx([0.1, 0.1, 0.5, 0.6])          # selected box, not the shadow run
    assert context["region_reason"] is None


def test_no_authoritative_selection_means_no_region(tmp_path):
    iid, path = _image(tmp_path)
    assert loc.localize_image(iid, path, _ctx([(20, 10, 100, 60)], "cfg-shadow"), max_regions=10).status == "detected"
    context = load_context(iid)
    assert context["region"] is None and context["region_id"] is None
    assert context["region_reason"] == "No authoritative bird selection"


def test_revoked_selection_is_not_used(tmp_path):
    iid, path = _image(tmp_path)
    loc.localize_image(iid, path, _ctx([(20, 10, 100, 60)], "cfg-selected"), max_regions=10)
    assert select_region(iid, _rank0(iid), "test")["status"] == "selected"
    revoke_selection(iid, "withdrawn")
    assert load_context(iid)["region"] is None


def _eye(region_id, x):
    conn = db.get_connector()
    run = conn.execute_returning(
        "INSERT INTO image_keypoint_runs (region_id, provider_key, provider_version, provider_config_hash, pass, status, is_current) "
        "VALUES (?, 'bird_head_pose', 'test/v0', 'cfg', 'full', 'detected', TRUE) RETURNING id", (region_id,))[0]["id"]
    conn.execute("INSERT INTO image_region_keypoints (keypoint_run_id, name, x, y, confidence, visible) "
                 "VALUES (?, 'left_eye', ?, 0.3, 0.95, TRUE)", (run, x))


def test_inspector_eyes_follow_the_selected_region(tmp_path):
    from modules.image_preview_overlays import get_image_preview_overlays

    iid, path = _image(tmp_path)
    loc.localize_image(iid, path, _ctx([(20, 10, 100, 60)], "cfg-selected"), max_regions=10)
    selected = _rank0(iid)
    _eye(selected, 0.25)
    assert select_region(iid, selected, "test")["status"] == "selected"
    loc.localize_image(iid, path, _ctx([(120, 40, 190, 95)], "cfg-shadow"), max_regions=10)
    _eye(_rank0(iid), 0.8)                                            # shadow-run eye must not show
    eyes = get_image_preview_overlays(db, iid)["eye_keypoints"]
    assert [p["x"] for p in eyes["points"]] == [0.25]
    revoke_selection(iid, "withdrawn")
    assert get_image_preview_overlays(db, iid)["eye_keypoints"] is None
