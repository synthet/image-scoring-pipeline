#!/usr/bin/env python3
"""
Hit MCP SSE Starlette app with GET/POST/DELETE on /sse (TestClient).

Useful to confirm POST is allowed (not 405) for a given FastMCP version.

Usage:
  python scripts/debug/probe_mcp_sse_methods.py
"""
from __future__ import annotations

from starlette.testclient import TestClient

from modules import mcp_server

app = mcp_server.create_mcp_sse_app(mount_path="/mcp")
client = TestClient(app)

print("GET /sse:")
print(client.get("/sse").status_code)

print("POST /sse:")
print(client.post("/sse", content="{}").status_code)

print("DELETE /sse:")
print(client.delete("/sse").status_code)
