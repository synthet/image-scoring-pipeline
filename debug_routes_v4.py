from fastapi import FastAPI
import gradio as gr
from modules import mcp_server
import os
from starlette.routing import Route, Mount

app = FastAPI()

# Create MCP app
mcp_sse_app = mcp_server.create_mcp_sse_app(mount_path='/mcp')

# 1. Mount MCP BEFORE Gradio
app.mount('/mcp', mcp_sse_app)

# 2. Mount Gradio
with gr.Blocks() as demo:
    gr.Markdown('Test')
app = gr.mount_gradio_app(app, demo, path='/')

from starlette.testclient import TestClient
client = TestClient(app)

print('\nTesting POST /mcp/sse (should reach messages handler):')
# Using a host header that avoids the transport security warning if possible, 
# although our script already showed it reaches the right place.
try:
    resp = client.post('/mcp/sse', content='{}', headers={'Host': '127.0.0.1'})
    print('Status:', resp.status_code)
except Exception as e:
    # We expect some validation error in the logs but the status code or the fact it didn't 404/405 is what matters.
    print('Caught expected validation error or response:', str(e)[:100])
