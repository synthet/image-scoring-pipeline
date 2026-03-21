#!/usr/bin/env python3
"""
Print FastMCP SSE sub-app routes and optionally GET /sse (event stream).

Usage:
  python scripts/debug/probe_fastmcp_sse_routes.py
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

mcp = FastMCP("test")
app = mcp.sse_app(mount_path="/mcp")
print("Routes:", [getattr(r, "path", str(r)) for r in app.routes])
for r in app.routes:
    if getattr(r, "path", None) == "/messages":
        print("Methods for /messages:", getattr(r, "methods", None))

with TestClient(app, base_url="http://testserver") as client:
    response = client.get("/sse", headers={"Accept": "text/event-stream"})
    print("GET /sse STATUS:", response.status_code)
    print("GET /sse TEXT (first 200 chars):", response.text[:200])
