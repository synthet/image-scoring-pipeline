# Suggested Commands

## Running the Application
- Start MCP Server: `python modules/mcp_server.py`
- Start WebUI: `run_webui.bat` or `python run_webui.bat` (wrapper) or `python webui.py` directly? Check script.
- Start Firebird container: `run_firebird.bat`

## Testing
- Run all tests: `pytest`
- Run fast tests (skip GPU/DB/Network): `pytest -m "not (gpu or db or network)"`

## Maintenance
- Install dependencies: `pip install -r requirements.txt`
- Build Docker: `docker-compose build`
