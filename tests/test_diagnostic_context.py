from PIL import Image
import pytest

from modules.visual_evidence.context import geometry_matches, load_context
from modules import db


def test_context_uses_accessible_source_variant_without_database_writes(monkeypatch, tmp_path):
    path = tmp_path / "image.png"
    Image.new("RGB", (32, 24)).save(path)
    class Connector:
        def query_one(self, sql, args):
            return {"id": 1, "file_path": str(path)} if "FROM images" in sql else None
    monkeypatch.setattr(db, "get_connector", lambda: Connector())
    monkeypatch.setattr(db, "get_resolved_path", lambda *a, **kw: "Z:\\offline\\image.png")
    result = load_context(1)
    assert result["path"] == str(path)
    assert result["source_hash"] != "missing"
    assert result["region"] is None


@pytest.mark.parametrize("orientation", range(1, 9))
def test_geometry_requires_matching_orientation_and_decode_route(orientation):
    width, height = (96, 64) if orientation < 5 else (64, 96)
    provenance = {"orientation": orientation, "decode_route": "direct", "display_width": width, "display_height": height, "rendition_hash": "original", "source_rendition_hash": "original"}
    context = {"region": [.1, .2, .8, .9], "region_provenance": provenance}
    assert geometry_matches(context, provenance)
    assert not geometry_matches(context, {**provenance, "orientation": (orientation % 8) + 1})
    assert not geometry_matches(context, {**provenance, "decode_route": "raw_preview"})
    assert not geometry_matches(context, {**provenance, "display_width": width * 2})
    assert not geometry_matches(context, {**provenance, "source_rendition_hash": "stale"})
