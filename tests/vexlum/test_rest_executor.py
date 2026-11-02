"""REST executor with a mocked httpx transport (no WebUI needed)."""

from __future__ import annotations

import json

import pytest

httpx = pytest.importorskip("httpx")

from modules.mcp.actions.errors import McpActionError  # noqa: E402
from modules.vexlum.executors import rest  # noqa: E402

RECORD = {
    "action_id": "api.images.update_image",
    "executor": {
        "kind": "rest",
        "method": "PATCH",
        "path": "/api/images/{image_id}",
        "operation_id": "update_image",
        "path_params": ["image_id"],
        "query_params": ["dry"],
        "header_params": [],
        "has_body": True,
    },
}


@pytest.fixture(autouse=True)
def _base(monkeypatch):
    monkeypatch.setenv("VEXLUM_API_URL", "http://api.test")
    monkeypatch.setenv("API_KEY", "k-123")


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_maps_path_query_body_and_api_key():
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-API-Key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    out = rest.run_rest(RECORD, {"image_id": 7, "dry": True, "body": {"rating": 4}}, client=_client(handler))
    assert seen["method"] == "PATCH"
    assert seen["url"] == "http://api.test/api/images/7?dry=true"
    assert seen["key"] == "k-123"
    assert seen["body"] == {"rating": 4}
    assert out == {"http_status": 200, "body": {"ok": True}, "truncated": False, "size_bytes": 12}


def test_describe_request_omits_api_key():
    out = rest.describe_request(RECORD, {"image_id": "a/b", "body": {}})
    assert out["would_request"]["url"] == "http://api.test/api/images/a%2Fb"
    assert "k-123" not in json.dumps(out)


def test_http_error_raises_with_status():
    with pytest.raises(rest.HttpError) as exc:
        rest.run_rest(RECORD, {"image_id": 1}, client=_client(lambda r: httpx.Response(404, json={"detail": "nope"})))
    assert exc.value.details["http_status"] == 404


def test_unreachable_is_webui_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(rest.WebuiUnavailableError):
        rest.run_rest(RECORD, {"image_id": 1}, client=_client(handler))


def test_truncates_large_bodies(monkeypatch):
    monkeypatch.setenv("VEXLUM_MAX_RESPONSE_BYTES", "50")
    out = rest.run_rest(RECORD, {"image_id": 1}, client=_client(lambda r: httpx.Response(200, json={"x": "y" * 500})))
    assert out["truncated"] is True
    assert len(out["body"]["preview"]) == 50


def test_missing_path_param():
    with pytest.raises(McpActionError):
        rest.build_request(RECORD, {})


def test_base_url_from_sse_env(monkeypatch):
    monkeypatch.delenv("VEXLUM_API_URL")
    monkeypatch.setenv("IMGSCORE_WEBUI_MCP_SSE_URL", "http://webui:7860/mcp/sse")
    assert rest.api_base_url() == "http://webui:7860"
