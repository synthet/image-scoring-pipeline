import asyncio
import json
import logging
from typing import List, Any, Dict

from pydantic import BaseModel, Field

try:
    from fastapi import WebSocket, WebSocketDisconnect
except ImportError:
    WebSocket = Any
    WebSocketDisconnect = Exception

logger = logging.getLogger(__name__)


class WebSocketEvent(BaseModel):
    """Schema for WebSocket push events broadcast to clients."""

    type: str
    data: dict = Field(default_factory=dict)


class EventManager:
    """
    Manages WebSocket connections and broadcasts events to connected clients.
    """
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, event_type: str, data: Any = None):
        """
        Broadcasts an event to all connected clients.
        """
        message = {
            "type": event_type,
            "data": data or {}
        }
        json_message = json.dumps(message)
        
        logger.debug(f"Broadcasting event: {event_type}")
        
        # Iterate over a copy to safe remove if needed
        for connection in self.active_connections[:]:
            try:
                await connection.send_text(json_message)
            except Exception as e:
                logger.error(f"Failed to send message to client: {e}")
                self.disconnect(connection)

    def broadcast_threadsafe(self, event_type: str, data: Any = None):
        """
        Broadcasts an event from a separate thread.
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
        
        # If no loop in current thread (likely), we need the main loop.
        # But grabbing the main loop globally is tricky without passing it.
        # However, usually uvicorn creates a loop.
        # A simple workaround for now: valid loop is needed.
        # Actually, best way is to let the main app set the loop on the manager.
        if hasattr(self, 'loop') and self.loop:
             asyncio.run_coroutine_threadsafe(self.broadcast(event_type, data), self.loop)
        else:
             logger.warning("No event loop attached to EventManager, skipping broadcast.")

    def set_loop(self, loop):
        self.loop = loop

# Global instance
event_manager = EventManager()
