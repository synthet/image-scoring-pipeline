"""Compatibility-release reads: API paths respect selected regions and flag rollback."""
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules import db, localization_legacy
from modules.api.routers.data_query import create_data_query_router
from modules.api.routers.public import create_public_api_router

LEGACY = {"detected": False}
SELECTED = {"x1": 10, "y1": 40, "x2": 60, "y2": 140,
            "img_w": 100, "img_h": 200, "conf": 0.8, "area_frac": 0.25}


class NormalizedRows:
    def __init__(self, rows, *, failure=False):
        self.rows = rows
        self.failure = failure
        self.calls = []
        self.freshness_enabled = False

    def query_one(self,sql,params=()):
        assert 'localization_authority_control' in sql
        return {'selection_freshness_enabled': self.freshness_enabled}

    def query(self, sql, params=()):
        self.calls.append((sql, params))
        if self.failure:
            raise RuntimeError("normalized storage unavailable")
        if 'image_bird_bbox_compat' in sql:
            return [{'image_id':row['image_id'],'bird_bbox':None} for row in self.rows if row['image_id'] in params]
        return [row for row in self.rows if row['image_id'] in params]


def selected_row(image_id=1, **extra):
    row = dict(image_id=image_id, selection_id=10, x1=0.1, y1=0.2, x2=0.6, y2=0.7,
               confidence=0.8, display_width=100, display_height=200, legacy_payload=None)
    row.update(extra)
    return row


@pytest.fixture
def api_reads(monkeypatch):
    row = {"id": 1, "file_path": "/test/photo.nef", "bird_bbox": deepcopy(LEGACY)}
    normalized = NormalizedRows([selected_row()])
    monkeypatch.setattr(db, "get_connector", lambda: normalized)
    monkeypatch.setattr(db, "get_images_paginated_with_count", lambda **kw: ([row], 1))
    for name in ("get_batch_image_phase_statuses", "get_batch_image_embedding_presence",
                 "get_batch_image_model_scores", "get_batch_resolved_image_keywords",
                 "compute_image_data_quality_flags_batch", "compute_image_data_quality_flags",
                 "get_image_phase_statuses", "get_image_model_scores"):
        monkeypatch.setattr(db, name, lambda *args, **kwargs: {})
    monkeypatch.setattr(db, "get_resolved_image_keywords", lambda *a, **kw: "")
    monkeypatch.setattr(db, "get_all_paths", lambda *a: [])
    monkeypatch.setattr(db, "get_resolved_path", lambda *a, **kw: row['file_path'])
    monkeypatch.setattr(db, "get_image_technical_failure", lambda *a: None)

    class Connection:
        def cursor(self):
            return self

        def execute(self, sql, params=()):
            assert sql.startswith("SELECT * FROM images WHERE id")

        def fetchone(self):
            return deepcopy(row)

        def close(self):
            pass

    monkeypatch.setattr(db, "get_db", Connection)
    app = FastAPI()
    app.include_router(create_data_query_router(), prefix="/api")
    app.include_router(create_public_api_router())
    with TestClient(app) as client:
        yield client, normalized, row


@pytest.mark.parametrize("path", ["/api/images", "/public/api/images", "/api/images/1", "/public/api/images/1"])
@pytest.mark.parametrize("enabled", [False, True])
def test_api_bbox_authority_and_flag_rollback(api_reads, monkeypatch, path, enabled):
    client, normalized, original = api_reads
    monkeypatch.setattr(localization_legacy, "read_normalized_first_enabled", lambda: enabled)
    response = client.get(path)
    assert response.status_code == 200
    body = response.json()
    image = body['images'][0] if 'images' in body else body
    assert image['bird_bbox'] == (SELECTED if enabled else LEGACY)
    assert len(normalized.calls) == int(enabled)
    assert original['bird_bbox'] == LEGACY, 'serialization must not alter cached database rows'


def test_batch_preserves_selection_import_and_shadow_authority():
    rows = [{"id": image_id, "bird_bbox": {"old": image_id}} for image_id in range(1, 7)]
    normalized = NormalizedRows([
        selected_row(1),
        dict(image_id=2, selection_id=None, legacy_payload={"detected": False}),
        dict(image_id=3, selection_id=None, legacy_payload=None),
        selected_row(4, display_width=None, legacy_payload={"detected": False}),
        dict(image_id=5, selection_id=None, legacy_payload={"detected": False, "error": "decode_error"}),
    ])
    localization_legacy.overlay_bird_bboxes(rows, conn=normalized, prefer_normalized=True)
    assert [row['bird_bbox'] for row in rows] == [
        SELECTED, {"detected": False}, {"old": 3}, {"old": 4},
        {"detected": False, "error": "decode_error"}, {"old": 6},
    ]
    assert len(normalized.calls) == 1


def test_batch_queries_scale_with_pages_not_image_count():
    rows = [{"id": image_id, "bird_bbox": None} for image_id in range(1, 502)]
    rows.append({"ID": 1, "bird_bbox": LEGACY})
    normalized = NormalizedRows([selected_row(1), selected_row(501)])
    localization_legacy.overlay_bird_bboxes(rows, conn=normalized, prefer_normalized=True)
    assert len(normalized.calls) == 2
    requested = [image_id for _, params in normalized.calls for image_id in params[2:]]
    assert requested == list(range(1, 502)), 'deduplicate IDs without losing row order'
    assert rows[0]['bird_bbox'] == rows[-1]['bird_bbox'] == rows[500]['bird_bbox'] == SELECTED
    assert rows[1]['bird_bbox'] is None


def test_batch_both_flags_off_never_queries_normalized_geometry(monkeypatch):
    # Reading the independent control is necessary even with normalized-first
    # off. Neither geometry storage nor the compatibility view may be read.
    normalized = NormalizedRows([])
    monkeypatch.setattr(db, 'get_connector', lambda: normalized)
    rows = [{"id": 1, "bird_bbox": None}, {"id": 2}, {"id": 3, "bird_bbox": LEGACY}]
    before = deepcopy(rows)
    localization_legacy.overlay_bird_bboxes(rows, prefer_normalized=False)
    assert rows == before
    assert normalized.calls == []


@pytest.mark.parametrize('path',['/api/images','/public/api/images','/api/images/1','/public/api/images/1'])
def test_independent_freshness_cannot_be_bypassed_by_normalized_flag_off(api_reads,monkeypatch,path):
    client,normalized,_ = api_reads
    normalized.freshness_enabled = True
    monkeypatch.setattr(localization_legacy,'read_normalized_first_enabled',lambda:False)
    response = client.get(path)
    assert response.status_code == 200
    body = response.json()
    image = body['images'][0] if 'images' in body else body
    assert image['bird_bbox'] is None


def test_batch_storage_outage_retains_legacy_values(caplog):
    rows = [{"id": 1, "bird_bbox": LEGACY}, {"id": 2, "bird_bbox": None}]
    before = deepcopy(rows)
    localization_legacy.overlay_bird_bboxes(rows, conn=NormalizedRows([], failure=True), prefer_normalized=True)
    assert rows == before
    assert 'normalized lookup failed' in caplog.text


def test_batch_empty_input_does_not_open_a_connector(monkeypatch):
    def forbidden():
        pytest.fail('empty response opened a connector')

    monkeypatch.setattr(db, 'get_connector', forbidden)
    localization_legacy.overlay_bird_bboxes([], prefer_normalized=True)


@pytest.mark.parametrize('enabled', [False, True])
def test_evidence_overlay_uses_the_same_authority_as_image_details(api_reads, monkeypatch, enabled):
    import numpy as np

    from modules.visual_evidence import service

    client, normalized, _ = api_reads
    monkeypatch.setattr(localization_legacy, 'read_normalized_first_enabled', lambda: enabled)
    monkeypatch.setattr(service, '_load_grey_from_thumbnail', lambda path: np.ones((40, 20), dtype=np.uint8))
    # Artifact versions hash the preview's source identity; the preview here is faked.
    monkeypatch.setattr('modules.rendition.source_identity', lambda path: ('preview-hash', 'v1'))

    class Connection:
        def cursor(self):
            return self

        def execute(self, sql, params=()):
            assert sql.startswith('SELECT thumbnail_path, bird_bbox')

        def fetchone(self):
            return '/test/thumbnail.jpg', deepcopy(LEGACY)

        def close(self):
            pass

    monkeypatch.setattr(db, 'get_db', Connection)
    response = client.get('/api/images/1/evidence')
    assert response.status_code == 200
    assert response.json()['region_bbox'] == (SELECTED if enabled else LEGACY)
    assert len(normalized.calls) == int(enabled)


def test_evidence_missing_image_returns_404_without_normalized_lookup(api_reads, monkeypatch):
    client, normalized, _ = api_reads
    monkeypatch.setattr(localization_legacy, 'read_normalized_first_enabled', lambda: True)

    class Connection:
        def cursor(self):
            return self

        def execute(self, sql, params=()):
            pass

        def fetchone(self):
            return None

        def close(self):
            pass

    monkeypatch.setattr(db, 'get_db', Connection)
    assert client.get('/api/images/1/evidence').status_code == 404
    assert not normalized.calls
