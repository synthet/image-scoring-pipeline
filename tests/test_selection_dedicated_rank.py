"""Unit tests for the dedicated within-stack culling rank (no GPU/DB).

``culling.dedicated_rank`` (default off) ranks stack members by a percentile-
rescaled ``liqe``/``spaq``/``topiq`` blend instead of ``score_general``.
See docs/reports/model-selection-findings-2026-10-02.md.
"""

from __future__ import annotations

import pytest

from modules import selection
from modules.score_normalization import rescale_percentile
from modules.selection import (
    DEDICATED_RANK_FIELD,
    DEFAULT_DEDICATED_RANK_WEIGHTS,
    apply_dedicated_rank,
    dedicated_rank_value,
)
from modules.score_normalization import DEFAULT_PERCENTILE_ANCHORS as A


def _ok(v):
    return {"normalized": v, "raw_score": v, "status": "success", "is_shadow": False}


def _resc(model, v):
    return rescale_percentile(v, A[model]["p02"], A[model]["p98"])


def test_default_weights_match_plan():
    assert DEFAULT_DEDICATED_RANK_WEIGHTS == {"liqe": 0.55, "spaq": 0.30, "topiq": 0.15}


def test_value_is_weighted_blend_of_rescaled_scores():
    entries = {"liqe": _ok(0.8), "spaq": _ok(0.5), "topiq": _ok(0.6), "ava": _ok(0.9)}
    expected = (
        0.55 * _resc("liqe", 0.8) + 0.30 * _resc("spaq", 0.5) + 0.15 * _resc("topiq", 0.6)
    )
    assert dedicated_rank_value(entries, DEFAULT_DEDICATED_RANK_WEIGHTS) == pytest.approx(expected)


def test_value_renormalizes_over_present_models():
    entries = {"liqe": _ok(0.8), "spaq": _ok(0.5)}  # topiq missing
    expected = (0.55 * _resc("liqe", 0.8) + 0.30 * _resc("spaq", 0.5)) / 0.85
    assert dedicated_rank_value(entries, DEFAULT_DEDICATED_RANK_WEIGHTS) == pytest.approx(expected)


def test_value_ignores_failed_and_null_rows():
    entries = {
        "liqe": {"normalized": 0.9, "status": "failed"},
        "spaq": {"normalized": None, "status": "success"},
        "topiq": _ok(0.6),
    }
    assert dedicated_rank_value(entries, DEFAULT_DEDICATED_RANK_WEIGHTS) == pytest.approx(
        _resc("topiq", 0.6)
    )


def test_value_none_when_no_usable_model():
    assert dedicated_rank_value({}, DEFAULT_DEDICATED_RANK_WEIGHTS) is None
    assert dedicated_rank_value({"ava": _ok(0.9)}, DEFAULT_DEDICATED_RANK_WEIGHTS) is None


def test_apply_reorders_against_score_general_and_falls_back():
    # img 1 wins on score_general, img 2 wins on the dedicated blend; img 3 has no rows.
    images = [
        {"id": 1, "score_general": 0.9},
        {"id": 2, "score_general": 0.5},
        {"id": 3, "score_general": 0.42},
    ]
    ims_map = {
        1: {"liqe": _ok(0.4), "spaq": _ok(0.3), "topiq": _ok(0.45)},
        2: {"liqe": _ok(0.95), "spaq": _ok(0.7), "topiq": _ok(0.65)},
    }
    n = apply_dedicated_rank(images, ims_map, DEFAULT_DEDICATED_RANK_WEIGHTS, "score_general")
    assert n == 2
    by_id = {im["id"]: im for im in images}
    assert by_id[3][DEDICATED_RANK_FIELD] == 0.42  # fallback keeps score_general
    ranked = sorted(images, key=lambda im: -selection.blended_rank_value(im, DEDICATED_RANK_FIELD, 0.0))
    assert [im["id"] for im in ranked][0] == 2


def test_cfg_default_off(monkeypatch):
    monkeypatch.setattr(selection, "get_config_value", lambda key, default=None: default)
    cfg = selection._dedicated_rank_cfg()
    assert cfg == {"enabled": False, "weights": DEFAULT_DEDICATED_RANK_WEIGHTS}


def test_cfg_sanitizes_weights(monkeypatch):
    raw = {"enabled": True, "weights": {"liqe": 0.7, "spaq": "bad", "topiq": -1, "ava": 0.3}}
    monkeypatch.setattr(selection, "get_config_value", lambda key, default=None: raw)
    cfg = selection._dedicated_rank_cfg()
    assert cfg == {"enabled": True, "weights": {"liqe": 0.7, "ava": 0.3}}


def test_cfg_empty_weights_fall_back_to_default(monkeypatch):
    raw = {"enabled": True, "weights": {"liqe": 0}}
    monkeypatch.setattr(selection, "get_config_value", lambda key, default=None: raw)
    assert selection._dedicated_rank_cfg()["weights"] == DEFAULT_DEDICATED_RANK_WEIGHTS


@pytest.mark.parametrize(
    "enabled, expected_picks",
    [(False, {1, 2}), (True, {3, 4})],
)
def test_run_flag_controls_within_stack_order(monkeypatch, enabled, expected_picks):
    """Flag off keeps score_general order; flag on ranks by the dedicated blend."""
    from unittest.mock import MagicMock, patch

    from modules.selection import SelectionConfig, SelectionService

    real_get = selection.get_config_value

    def fake_get(key, default=None):
        if key == "culling.dedicated_rank":
            return {"enabled": enabled}
        if key.startswith("culling."):
            return default
        return real_get(key, default=default)

    monkeypatch.setattr(selection, "get_config_value", fake_get)

    def images():
        return [
            {"id": i, "stack_id": 100, "score_general": 1.0 - i / 10, "file_path": f"/m/{i}.jpg"}
            for i in (1, 2, 3, 4)
        ]

    # Model scores rise with id, i.e. the reverse of score_general.
    ims_map = {
        i: {"liqe": _ok(0.3 + 0.15 * i), "spaq": _ok(0.2 + 0.1 * i), "topiq": _ok(0.4 + 0.05 * i)}
        for i in (1, 2, 3, 4)
    }

    svc = SelectionService()
    svc._cluster_engine.cluster_images = lambda *a, **k: iter(())
    cfg = SelectionConfig(
        pick_fraction=0.5, two_level_enabled=False, sub_cluster_distance_threshold=None
    )
    persist = MagicMock()
    with patch("os.path.exists", return_value=True), \
         patch("modules.utils.convert_path_to_local", return_value="/m"), \
         patch("modules.db.list_folder_paths_under_scope", return_value=["/m"]), \
         patch("modules.db.get_images_by_folder", side_effect=[images(), images()]), \
         patch("modules.db.get_exif_fields_for_quality_tiebreak", return_value={}), \
         patch("modules.db.get_batch_image_model_scores", return_value=ims_map), \
         patch("modules.db.batch_update_cull_decisions", persist), \
         patch("modules.selection.write_selection_metadata", return_value=(True, True)):
        summary = svc.run("/m", cfg=cfg)

    assert summary.status == "completed"
    decisions = persist.call_args.args[0]
    assert {img_id for img_id, d, _ in decisions if d == "pick"} == expected_picks
