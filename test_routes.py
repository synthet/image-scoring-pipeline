from mcp.server.fastmcp import FastMCP
mcp = FastMCP("test")
app = mcp.sse_app(mount_path="/mcp")
print("Routes:", [r.path for r in app.routes])
print("Methods for /messages:", [r.methods for r in app.routes if r.path == '/messages'])
