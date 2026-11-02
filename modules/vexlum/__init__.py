"""Vexlum: single search -> resolve -> execute entry point (MCP + CLI).

One catalog over every backend capability:

* ``tool``    — Python MCP tools (``modules/mcp_server.py`` + action registry)
* ``api``     — REST operations generated from ``docs/reference/api/openapi.yaml``
* ``db``      — direct PostgreSQL access (schema, SELECT, write SQL)
* ``browser`` — Playwright actions, executed by the TS host (``mcp-server/``)

Contract: docs/technical/VEXLUM_MCP.md
"""

from __future__ import annotations

SERVER_NAME = "vexlum"
TOOL_SEARCH = "search"
TOOL_RESOLVE = "resolve"
TOOL_EXECUTE = "execute"
# Deprecated aliases kept for one release (old is-be-mcp contract).
TOOL_DISPATCH_ALIAS = "dispatch"
TOOL_SSE_STATUS_ALIAS = "sse_status"

__all__ = [
    "SERVER_NAME",
    "TOOL_SEARCH",
    "TOOL_RESOLVE",
    "TOOL_EXECUTE",
    "TOOL_DISPATCH_ALIAS",
    "TOOL_SSE_STATUS_ALIAS",
]
