"""
DEPRECATED — MCP router / compact server (search + dispatch, be_* on router profile).
Running this module now starts vexlum; ``create_router_mcp`` is kept for existing imports/tests.

Use: mcp-server/dist/vexlum.js or ``python -m modules.vexlum mcp`` (docs/technical/VEXLUM_MCP.md).
"""

from __future__ import annotations

import logging
import os
import sys

try:
    from mcp.server.fastmcp import FastMCP

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

from modules.mcp.names import BE_MCP, BE_ROUTER
from modules.mcp.router_tools import register_tools_for_profile

logger = logging.getLogger(__name__)


def _server_name() -> str:
    prof = (os.environ.get("MCP_TOOL_PROFILE") or "router").strip().lower()
    return BE_MCP if prof == "compact" else BE_ROUTER


def create_router_mcp() -> FastMCP:
    name = _server_name()
    mcp = FastMCP(name)
    register_tools_for_profile(mcp)
    return mcp


async def run_server() -> None:
    if not MCP_AVAILABLE:
        print("Error: MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
        return
    mcp = create_router_mcp()
    await mcp.run_stdio_async()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    # DEPRECATED entry point: serve vexlum (search/resolve/execute) instead.
    logger.warning(
        "python -m modules.mcp.router_server is deprecated; starting vexlum. "
        "Use `python -m modules.vexlum mcp` or mcp-server/dist/vexlum.js (docs/technical/VEXLUM_MCP.md)."
    )
    from modules.vexlum.mcp_stdio import run_stdio

    run_stdio()
