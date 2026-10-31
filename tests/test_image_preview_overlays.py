"""Cached preview overlays: no inference and no database required."""

from types import SimpleNamespace
from unittest.mock import Mock

from modules.image_preview_overlays import get_image_preview_overlays


def test_cached_af_and_normalized_visible_eyes():
    af = {"mode": "Wide (L)", "in_focus": True, "box": {"left": .1, "top": .2, "width": .3, "height": .4}}
    connector = Mock()
    connector.query.return_value = [
        {"display_width": 1000, "display_height": 800, "name": "left_eye", "x": .4, "y": .3, "confidence": .95},
    ]
    database = SimpleNamespace(get_connector=lambda: connector, get_image_exif=lambda _: {"af_metadata": af})
    result = get_image_preview_overlays(database, 71662)
    assert result["af_metadata"] == af
    assert result["eye_keypoints"] == {"display_width": 1000, "display_height": 800, "points": [{"name": "left_eye", "x": .4, "y": .3, "confidence": .95}]}
    sql, params = connector.query.call_args.args
    assert params == (71662, .8)
    # Eyes belong to the selected, fresh bird region, never a newer shadow run (#714).
    for predicate in ("s.revoked_at IS NULL", "localization_selection_is_fresh(s.id)", "kr.is_current", "k.visible"):
        assert predicate in sql


def test_missing_or_invalid_artifacts_are_unavailable():
    connector = Mock()
    connector.query.return_value = [
        {"display_width": 1000, "display_height": 800, "name": "left_eye", "x": 1.4, "y": .3, "confidence": .95},
        {"display_width": 1000, "display_height": 800, "name": "right_eye", "x": .4, "y": .3, "confidence": .2},
    ]
    database = SimpleNamespace(get_connector=lambda: connector, get_image_exif=lambda _: None)
    assert get_image_preview_overlays(database, 1) == {"af_metadata": None, "eye_keypoints": None}


def test_older_schema_keeps_af_available():
    class MissingTable(Exception):
        pgcode = "42P01"

    af = {"mode": "Single"}
    connector = Mock()
    connector.query.side_effect = MissingTable()
    database = SimpleNamespace(get_connector=lambda: connector, get_image_exif=lambda _: {"af_metadata": af})
    assert get_image_preview_overlays(database, 1) == {"af_metadata": af, "eye_keypoints": None}
