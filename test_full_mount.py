from fastapi import FastAPI
import gradio as gr
from modules import mcp_server
import os

app = FastAPI()

# 1. Mount MCP
mcp_sse_app = mcp_server.create_mcp_sse_app(mount_path='/mcp')
app.mount('/mcp', mcp_sse_app)

# 2. Mount Gradio
with gr.Blocks() as demo:
    gr.Markdown('Test')
app = gr.mount_gradio_app(app, demo, path='/')

# 3. Test
from starlette.testclient import TestClient
client = TestClient(app)

print('POST /mcp/sse:')
resp = client.post('/mcp/sse', content='{}')
print('Status:', resp.status_code)
