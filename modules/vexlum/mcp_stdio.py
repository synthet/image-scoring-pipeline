"""FastMCP surface for vexlum: ``search``, ``resolve``, ``execute`` (+ deprecated ``dispatch``).

Used for the Python stdio server (``python -m modules.vexlum mcp``) and the WebUI SSE mount
(``/mcp/sse``). Browser actions need the TS host; here they return a ``playwright_delegate``
envelope.
"""

from __future__ import annotations

import logging
from typing import Any

from modules.vexlum import SERVER_NAME, service

logger = logging.getLogger(__name__)

SEARCH_DOC = (
    "Step 1 of 3. BM25 search over every Vexlum Scoring capability: Python tools, REST API "
    "(api.*), PostgreSQL (db.*), browser (browser.*). Never executes anything. Filter with "
    "source=tool|api|db|browser|system, category, tier=read|write|destructive."
)
RESOLVE_DOC = (
    "Step 2 of 3. Full contract for one action_id: input_schema, tier, required confirmation, "
    "example call. Accepts legacy tool names, REST operationIds and 'METHOD /path'."
)
EXECUTE_DOC = (
    "Step 3 of 3. Run an action. Tiers: read runs immediately; write needs confirmed=true; "
    "destructive needs VEXLUM_ALLOW_ELEVATED=1 on the server, a dry_run=true call (returns "
    "confirm_token), then confirmed=true + confirm_token with identical arguments."
)


async def _offload(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run sync service code off the event loop (WebUI SSE: REST calls hit the same server)."""
    import anyio

    return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))


def register_vexlum_tools(server: Any, *, include_deprecated: bool = True) -> None:
    try:
        from mcp.types import ToolAnnotations

        ro: Any = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
        rw: Any = ToolAnnotations(readOnlyHint=False, destructiveHint=True)
    except Exception:  # noqa: BLE001
        ro = rw = None

    def _tool(annotations: Any, description: str):
        kwargs: dict[str, Any] = {"description": description}
        if annotations is not None:
            kwargs["annotations"] = annotations
        return server.tool(**kwargs)

    @_tool(ro, SEARCH_DOC)
    async def search(
        query: str = "",
        limit: int = 10,
        source: str | None = None,
        category: str | None = None,
        tier: str | None = None,
        include_schemas: bool = False,
    ) -> dict:
        return await _offload(service.search, query, limit=limit, source=source, category=category, tier=tier,
                              include_schemas=include_schemas)

    @_tool(ro, RESOLVE_DOC)
    async def resolve(action_id: str) -> dict:
        return await _offload(service.resolve, action_id)

    @_tool(rw, EXECUTE_DOC)
    async def execute(
        action_id: str,
        arguments: dict | None = None,
        dry_run: bool = False,
        confirmed: bool = False,
        confirm_token: str | None = None,
        request_id: str | None = None,
    ) -> dict:
        return await _offload(service.execute, action_id, arguments, dry_run=dry_run, confirmed=confirmed,
                              confirm_token=confirm_token, request_id=request_id)

    if include_deprecated:

        @_tool(rw, "DEPRECATED alias of execute (old is-be-mcp contract). Use search -> resolve -> execute.")
        async def dispatch(
            action_id: str,
            arguments: dict | None = None,
            dry_run: bool = False,
            confirmed: bool = False,
            request_id: str | None = None,
            allow_deprecated: bool = False,
            expected_version: int | None = None,
        ) -> dict:
            del allow_deprecated, expected_version
            return await _offload(service.dispatch_alias, action_id, arguments, dry_run=dry_run, confirmed=confirmed,
                                          request_id=request_id)


def _fastmcp_class() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP

        return FastMCP
    except ImportError:
        from mcp.server.mcpserver import MCPServer  # mcp 2.x

        return MCPServer


def create_server(**kwargs: Any) -> Any:
    server = _fastmcp_class()(SERVER_NAME, **kwargs)
    register_vexlum_tools(server)
    return server


def run_stdio() -> None:
    import asyncio

    try:
        from modules.mcp_server import prepare_mcp_embedded

        prepare_mcp_embedded()
    except Exception:  # noqa: BLE001 - DB-less tools still work
        logger.warning("DB init failed; db/tool actions will report it per call", exc_info=True)
    server = create_server()
    asyncio.run(server.run_stdio_async())
