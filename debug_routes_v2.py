from fastapi import FastAPI
import gradio as gr
from modules import mcp_server
import os

app = FastAPI()

# Create MCP app
mcp_sse_app = mcp_server.create_mcp_sse_app(mount_path='/mcp')

# 1. Mount MCP BEFORE Gradio
app.mount('/mcp', mcp_sse_app)

# 2. Mount Gradio
with gr.Blocks() as demo:
    gr.Markdown('Test')
app = gr.mount_gradio_app(app, demo, path='/')

print('Final Routes:')
for r in app.routes:
    path = getattr(r, 'path', 'N/A')
    name = type(r).__name__
    methods = getattr(r, 'methods', 'N/A')
    print(f'{name}: {path} {methods}')

from starlette.testclient import TestClient
client = TestClient(app)
print('\nTesting POST /mcp/sse:')
resp = client.post('/mcp/sse', content='{}')
print('Status:', resp.status_code)
