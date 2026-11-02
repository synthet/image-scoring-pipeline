"""Unified catalog: every legacy tool and every REST operation resolves to a vexlum action."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from modules.vexlum import catalog  # noqa: E402
from modules.vexlum.providers.rest import area_for_path, short_name  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def cat():
    catalog.clear_catalog_cache()
    return catalog.get_catalog(refresh=True)


def test_action_ids_unique(cat):
    ids = [a["action_id"] for a in cat["actions"]]
    assert len(ids) == len(set(ids))


def test_every_source_present(cat):
    sources = {a["source"] for a in cat["actions"]}
    assert {"tool", "api", "db", "system"} <= sources


def test_every_rest_operation_is_an_action(cat):
    spec = yaml.safe_load((ROOT / "docs/reference/api/openapi.yaml").read_text(encoding="utf-8"))
    op_ids = {
        op["operationId"]
        for item in spec["paths"].values()
        for method, op in item.items()
        if method in ("get", "post", "put", "patch", "delete")
    }
    rest = {a["executor"]["operation_id"] for a in cat["actions"] if a["source"] == "api"}
    assert op_ids == rest


def test_every_legacy_tool_resolves(cat):
    tools = json.loads((ROOT / "mcp/tool_catalog.json").read_text(encoding="utf-8"))["tools"]
    missing = [t["name"] for t in tools if catalog.resolve_id(t["name"]) is None]
    assert missing == []


def test_tiers_are_valid_and_dangerous_tools_gated(cat):
    by_id = cat["by_id"]
    assert all(a["tier"] in ("read", "write", "destructive") for a in cat["actions"])
    assert by_id["db.execute"]["tier"] == "destructive"
    assert by_id["db.query"]["tier"] == "read"
    assert by_id[catalog.resolve_id("prune_missing_files")]["tier"] == "destructive"
    assert by_id[catalog.resolve_id("run_processing_job")]["tier"] == "write"  # tool_catalog says read_only
    assert by_id[catalog.resolve_id("POST /api/shutdown")]["tier"] == "destructive"
    assert by_id[catalog.resolve_id("POST /api/runs/plan/preview")]["tier"] == "read"
    assert by_id[catalog.resolve_id("DELETE /api/images/{image_id}")]["tier"] == "destructive"


def test_resolve_id_variants(cat):
    assert catalog.resolve_id("diagnostics.get_error_summary") == "diagnostics.get_error_summary"
    assert catalog.resolve_id("get_error_summary") == "diagnostics.get_error_summary"
    assert catalog.resolve_id("wrong.get_error_summary") == "diagnostics.get_error_summary"
    assert catalog.resolve_id("GET /api/stats") == "api.stats.get_stats"
    assert catalog.resolve_id("definitely_not_a_thing") is None


def test_snapshot_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("VEXLUM_CACHE_DIR", str(tmp_path))
    catalog.clear_catalog_cache()
    first = catalog.get_catalog(refresh=True)
    assert not first["from_snapshot"]
    assert list(tmp_path.glob("catalog-*.json"))
    catalog.clear_catalog_cache()
    second = catalog.get_catalog(refresh=True)
    assert second["from_snapshot"]
    assert [a["action_id"] for a in second["actions"]] == [a["action_id"] for a in first["actions"]]
    catalog.clear_catalog_cache()


def test_short_name_and_area():
    assert short_name("start_scoring_api_scoring_start_post", "/api/scoring/start", "post") == "start_scoring"
    assert short_name("custom", "/api/x", "get") == "custom"
    assert area_for_path("/api/images/{image_id}/geocode/reverse") == "images"
    assert area_for_path("/api/raw-preview") == "raw_preview"
