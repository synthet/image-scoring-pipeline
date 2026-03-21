#!/usr/bin/env python3
"""
Minimal FastAPI app mounting MCP SSE + Gradio; POST /mcp/sse with TestClient.

Used to debug mount order / routing when MCP and Gradio share an app.

Usage:
  python scripts/debug/probe_gradio_mcp_mount.py
"""
from __future__ import annotations

import gradio as gr
from fastapi import FastAPI
from starlette.testclient import TestClient

from modules import mcp_server

app = FastAPI()
mcp_sse_app = mcp_server.create_mcp_sse_app(mount_path="/mcp")
app.mount("/mcp", mcp_sse_app)

with gr.Blocks() as demo:
    gr.Markdown("Test")
app = gr.mount_gradio_app(app, demo, path="/")

client = TestClient(app)
print("POST /mcp/sse:")
resp = client.post("/mcp/sse", content="{}")
print("Status:", resp.status_code)
