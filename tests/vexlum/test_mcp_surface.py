"""The FastMCP surface (stdio + WebUI SSE) registers search / resolve / execute (+ dispatch alias)."""

from __future__ import annotations

import pytest

from modules.mcp_server import MCP_AVAILABLE

requires_mcp_sdk = pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP v1 SDK unavailable (mcp 2.x)")


def _tool_names(server) -> set[str]:
    mgr = getattr(server, "_tool_manager", None)
    return set(getattr(mgr, "_tools", {}).keys())


@requires_mcp_sdk
def test_create_server_tools():
    from modules.vexlum.mcp_stdio import create_server

    assert _tool_names(create_server()) == {"search", "resolve", "execute", "dispatch"}


@requires_mcp_sdk
def test_webui_sse_serves_vexlum():
    from modules import mcp_server

    mcp_server._compact_mcp_sse = None
    sse = mcp_server._get_compact_mcp_sse()
    assert sse.name == "vexlum"
    assert {"search", "resolve", "execute"} <= _tool_names(sse)
