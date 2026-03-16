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

print('\nTesting GET /mcp/sse:')
resp = client.get('/mcp/sse')
print('Status:', resp.status_code)

print('\nTesting POST /mcp/sse:')
# Note: it might return 400 Bad Request if it reaches the real handler but has no data, 
# which is BETTER than 404 or 405.
resp = client.post('/mcp/sse', content='{}')
print('Status:', resp.status_code)

print('\nTesting DELETE /mcp/sse:')
resp = client.delete('/mcp/sse')
print('Status:', resp.status_code)
