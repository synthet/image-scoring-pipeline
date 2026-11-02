"""search / resolve / execute without DB or WebUI (executors stubbed where they would reach out)."""

from __future__ import annotations

import pytest

pytest.importorskip("yaml")

from modules.vexlum import catalog, service  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _warm_catalog():
    catalog.get_catalog()


def test_search_ranks_error_summary_first():
    out = service.search("why did scoring fail", limit=3)
    assert out["results"][0]["action_id"] == "diagnostics.get_error_summary"
    assert out["results"][0]["tier"] == "read"


def test_search_filters():
    out = service.search("images", source="api", tier="read", limit=20)
    assert out["results"]
    assert all(r["source"] == "api" and r["tier"] == "read" for r in out["results"])
    assert all(r["tier"] == "read" for r in service.search("delete", read_only_only=True)["results"])


def test_empty_search_returns_catalog_overview():
    out = service.search("")
    assert out["catalog"]["total"] > 200


def test_resolve_contract_for_destructive():
    out = service.resolve("db.execute")
    assert out["status"] == "success"
    assert out["tier"] == "destructive"
    assert out["requires"]["confirm_token"] is True
    assert out["example"][0]["dry_run"] is True
    assert "query" in out["input_schema"]["properties"]


def test_resolve_unknown_has_suggestions():
    out = service.resolve("embedding statz")
    assert out["status"] == "error"
    assert out["code"] == "unknown_action"


def test_execute_validation_error():
    out = service.execute("db.query", {})
    assert out["status"] == "error"
    assert out["code"] == "validation_error"


def test_db_query_rejects_writes_before_db():
    out = service.execute("db.query", {"query": "DELETE FROM images"})
    assert out["code"] == "validation_error"


def test_write_requires_confirmation():
    out = service.execute("api.tagging.stop_tagging", {})
    assert out["code"] == "confirmation_required"
    assert out["tier"] == "write"


def test_destructive_dry_run_issues_token_and_real_run_needs_env(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "modules.vexlum.executors.rest.run_rest",
        lambda record, args, client=None: calls.append(args) or {"http_status": 200, "body": {}},
    )
    args = {"image_id": 5}
    dry = service.execute("api.images.delete_image", args, dry_run=True)
    assert dry["status"] == "success" and dry["dry_run"] is True
    token = dry["data"]["confirm_token"]
    assert dry["data"]["preview"]["would_request"]["method"] == "DELETE"
    assert calls == []

    blocked = service.execute("api.images.delete_image", args, confirmed=True, confirm_token=token)
    assert blocked["code"] == "policy_rejected"

    monkeypatch.setenv("VEXLUM_ALLOW_ELEVATED", "1")
    changed = service.execute("api.images.delete_image", {"image_id": 6}, confirmed=True, confirm_token=token)
    assert changed["code"] == "confirm_token_invalid"
    ok = service.execute("api.images.delete_image", args, confirmed=True, confirm_token=token)
    assert ok["status"] == "success"
    assert calls == [args]


def test_native_dry_run_passes_flag(monkeypatch):
    seen = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return {"would_delete": 0}

    monkeypatch.setattr("modules.mcp_server.prune_missing_files", fake, raising=False)
    aid = catalog.resolve_id("prune_missing_files")
    record = catalog.get_catalog()["by_id"][aid]
    assert record["native_dry_run"] is True
    assert "dry_run" not in record["input_schema"]["properties"]
    out = service.execute(aid, {}, dry_run=True)
    assert out["status"] == "success"
    assert seen == {"dry_run": True}
    assert "confirm_token" in out["data"]


def test_browser_execute_returns_playwright_delegate():
    out = service.execute("browser.snapshot", {})
    assert out["status"] == "proxy"
    assert out["code"] == "playwright_delegate"
    assert out["legacy_tool_name"] == "browser_snapshot"


def test_dispatch_alias_warns():
    out = service.dispatch_alias("system.categories", {})
    assert out["status"] == "success"
    assert any("deprecated" in w for w in out["warnings"])


def test_invoke_routes_tools():
    assert service.invoke("resolve", {"action_id": "db.query"})["action_id"] == "db.query"
    assert service.invoke("list", {"source": "db"})["count"] == 3
    assert service.invoke("nope")["code"] == "unknown_tool"
