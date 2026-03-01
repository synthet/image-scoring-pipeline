import pytest
import asyncio
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket
from modules.events import event_manager
from webui import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_websocket_connection():
    with client.websocket_connect("/ws/updates") as websocket:
        assert len(event_manager.active_connections) == 1
        
        # Test receiving a broadcast
        test_data = {"test": "data"}
        await event_manager.broadcast("test_event", test_data)
        
        data = websocket.receive_json()
        assert data["type"] == "test_event"
        assert data["data"] == test_data

@pytest.mark.asyncio
async def test_threadsafe_broadcast():
    # Mock loop for checking logic, but hard to fully integration test without running loop
    # This just ensures no crash
    event_manager.broadcast_threadsafe("test_thread", {})
