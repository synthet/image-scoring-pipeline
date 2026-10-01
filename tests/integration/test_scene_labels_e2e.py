"""E2E: scene route persistence against real PostgreSQL (spec 05 AC-5, AC-9; #412).

No model is loaded; a fixed ``SceneResult`` stands in for the classifier. ``pytest.mark.postgres``.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.postgres]

from modules import db  # noqa: E402
from modules.scene_route import SceneResult, get_scene_label, save_scene_label  # noqa: E402


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    yield


@pytest.fixture
def image_id():
    row = db.get_connector().execute_returning(
        "INSERT INTO images (file_path) VALUES (?) RETURNING id", ("/tmp/scene.jpg",))
    return int(row[0]["id"])


def _result(version, top, prob):
    return SceneResult(probs={top: prob, "other": round(1 - prob, 6)}, cosines={top: 0.3, "other": 0.2},
                       top_label=top, top_prob=prob, version=version)


def test_resolved_class_round_trips(image_id):
    save_scene_label(image_id, _result("v1", "wildlife_bird", 0.8), backend="hf_clip_b32",
                     rendition_hash="r1")
    row = get_scene_label(image_id, "v1")
    assert row["top_label"] == "wildlife_bird" and row["top_prob"] == pytest.approx(0.8)
    assert row["probs"]["wildlife_bird"] == pytest.approx(0.8) and row["rendition_hash"] == "r1"


def test_same_version_replaces_new_version_adds(image_id):
    save_scene_label(image_id, _result("v1", "wildlife_bird", 0.8), backend="hf_clip_b32")
    save_scene_label(image_id, _result("v1", "landscape", 0.6), backend="hf_clip_b32")
    save_scene_label(image_id, _result("v2", "landscape", 0.7), backend="openclip_l14")
    rows = db.get_connector().query(
        "SELECT scene_version, top_label FROM image_scene_labels WHERE image_id = ? ORDER BY scene_version",
        (image_id,))
    assert [(r["scene_version"], r["top_label"]) for r in rows] == [("v1", "landscape"), ("v2", "landscape")]


def test_rows_cascade_with_the_image(image_id):
    save_scene_label(image_id, _result("v1", "people", 0.9), backend="hf_clip_b32")
    db.get_connector().execute("DELETE FROM images WHERE id = ?", (image_id,))
    assert get_scene_label(image_id, "v1") is None
