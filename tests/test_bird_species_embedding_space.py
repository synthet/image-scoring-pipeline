"""#641: BioCLIP crop and full-frame embeddings must not share one embedding space.

Rollout invariant: full-frame and crop embeddings never share an embedding identity unless the
input mode is part of it. Crops (a selected region or the embedded detector's box) go to
``bioclip_2_crop``; only full frames go to ``bioclip_2_image``.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import modules.bird_species as bs
from modules.bird_detection import BBOX_NOT_DETECTED, bbox_scan_failed
from modules.bird_species import BirdSpeciesRunner, bioclip_input_mode
from modules.embedding_spaces import (
    BIOCLIP_CROP_SPACE_CODE,
    BIOCLIP_IMAGE_DIM,
    BIOCLIP_IMAGE_SPACE_CODE,
    SPACE_DIMS,
)

_BOX = {"x1": 1, "y1": 2, "x2": 30, "y2": 20, "conf": 0.8, "img_w": 40, "img_h": 30}


@pytest.mark.parametrize("region,last_bbox,mode", [
    ((0.1, 0.1, 0.5, 0.5), None, "region"),
    (None, _BOX, "detector_crop"),
    (None, dict(BBOX_NOT_DETECTED), "full_frame"),
    (None, bbox_scan_failed("detector_unavailable"), "full_frame"),
    (None, None, "full_frame"),
])
def test_input_mode_from_region_and_box(region, last_bbox, mode):
    assert bioclip_input_mode(region, last_bbox) == mode


def test_crop_space_is_registered_at_bioclip_dim():
    assert BIOCLIP_CROP_SPACE_CODE != BIOCLIP_IMAGE_SPACE_CODE
    assert SPACE_DIMS[BIOCLIP_CROP_SPACE_CODE] == BIOCLIP_IMAGE_DIM


def test_crop_space_seed_and_migration_match_registry():
    from modules import db_postgres

    seeded = {code: int(dim) for sql in db_postgres._SEED_EXTRA_EMBEDDING_SPACES_SQL
              for code, dim in re.findall(r"SELECT '([a-z0-9_]+)',\s*(\d+)", sql)}
    assert seeded[BIOCLIP_CROP_SPACE_CODE] == BIOCLIP_IMAGE_DIM

    src = (Path(__file__).resolve().parents[1] / "migrations" / "versions"
           / "0042_bioclip_crop_embedding_space.py").read_text(encoding="utf-8")
    assert re.search(r'down_revision\s*=\s*"0041"', src)
    assert re.search(rf'_CODE\s*=\s*"{BIOCLIP_CROP_SPACE_CODE}"', src)
    assert re.search(rf"_DIM\s*=\s*{BIOCLIP_IMAGE_DIM}\b", src)


def _persisted_space(monkeypatch, mode):
    calls = []
    monkeypatch.setattr(bs.db, "update_image_embeddings_batch_for_space",
                        lambda code, rows: calls.append((code, rows)) or len(rows))
    from modules import config

    monkeypatch.setattr(config, "get_config_section", lambda name: {})
    runner = BirdSpeciesRunner()
    runner.classifier = SimpleNamespace(last_image_embedding=np.zeros(BIOCLIP_IMAGE_DIM, dtype=np.float32),
                                        last_input_mode=mode, MODEL_ID="bioclip-2")
    runner._persist_bioclip_embedding(5)
    return [code for code, _rows in calls]


@pytest.mark.parametrize("mode,space", [
    ("region", BIOCLIP_CROP_SPACE_CODE),
    ("detector_crop", BIOCLIP_CROP_SPACE_CODE),
    ("full_frame", BIOCLIP_IMAGE_SPACE_CODE),
])
def test_persist_routes_each_input_mode_to_its_space(monkeypatch, mode, space):
    assert _persisted_space(monkeypatch, mode) == [space]


def test_persist_skips_unknown_input_mode(monkeypatch):
    """No input mode means no proof of identity: write nothing rather than mix spaces."""
    assert _persisted_space(monkeypatch, None) == []
