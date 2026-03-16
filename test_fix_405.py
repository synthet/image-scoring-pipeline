from modules import mcp_server
from starlette.testclient import TestClient

app = mcp_server.create_mcp_sse_app(mount_path='/mcp')
client = TestClient(app)

print("GET /sse:")
resp = client.get('/sse')
print(resp.status_code)

print("POST /sse:")
# We don't care if it fails with 400 or something, as long as it's not 405.
# The endpoint expects JSON for MCP.
resp = client.post('/sse', content='{}')
print(resp.status_code)

print("DELETE /sse:")
resp = client.delete('/sse')
print(resp.status_code)
