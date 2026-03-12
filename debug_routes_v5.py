from fastapi import FastAPI
import gradio as gr
from modules import mcp_server
import os
from starlette.routing import Route, Mount
from starlette.responses import Response

app = FastAPI()

# Mimic mcp_server logic
mcp_sse_app = mcp_server.create_mcp_sse_app(mount_path='/mcp')

# Find the mount
messages_mount = next((r for r in mcp_sse_app.routes if isinstance(r, Mount) and r.path == '/messages'), None)

async def sse_post_alias(request):
    scope = dict(request.scope)
    scope['path'] = '/messages'
    # Use request._send which we verified exists
    await messages_mount.handle(scope, request.receive, request._send)

# Replace the previous alias for testing
mcp_sse_app.routes = [r for r in mcp_sse_app.routes if r.path != '/sse' or 'POST' not in getattr(r, 'methods', [])]
mcp_sse_app.routes.insert(0, Route('/sse', endpoint=sse_post_alias, methods=['POST']))

# Mount
app.mount('/mcp', mcp_sse_app)
with gr.Blocks() as demo:
    gr.Markdown('Test')
app = gr.mount_gradio_app(app, demo, path='/')

from starlette.testclient import TestClient
client = TestClient(app)

print('\nTesting POST /mcp/sse:')
try:
    resp = client.post('/mcp/sse', content='{}', headers={'Host': '127.0.0.1'})
    print('Status:', resp.status_code)
except Exception as e:
    # If it's a validation error, it means we reached the handler!
    if 'Request validation failed' in str(e):
        print('Reached handler successfully (Validation failed as expected).')
    else:
        print('Error:', e)
