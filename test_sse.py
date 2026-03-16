from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

mcp = FastMCP('test')
app = mcp.sse_app(mount_path='/mcp')

with TestClient(app, base_url="http://testserver") as client:
    response = client.get('/sse', headers={'Accept': 'text/event-stream'})
    print("STATUS:", response.status_code)
    print("TEXT:", response.text[:200])
