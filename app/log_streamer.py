"""
This module provides the components needed to stream server logs
to a WebSocket client, such as a web UI.
"""
import asyncio
import json
import logging
from typing import Set
from app.web_ui_server import app
from websockets.server import ServerProtocol

logger = logging.getLogger(__name__)

class LogStreamer:
    """
    Manages WebSocket clients that are subscribed to log streams.
    """
    def __init__(self):
        self.clients: Set[ServerProtocol] = set()

    async def add_client(self, websocket: ServerProtocol):
        """Registers a new client WebSocket."""
        logger.info(f"Log streaming client connected: {websocket.remote_address}")
        self.clients.add(websocket)

    def remove_client(self, websocket: ServerProtocol):
        """Unregisters a client WebSocket."""
        logger.info(f"Log streaming client disconnected: {websocket.remote_address}")
        self.clients.remove(websocket)

    async def broadcast(self, message: str):
        """Sends a message to all registered clients."""
        if not self.clients:
            return
        
        # Create a task for each client to send the message concurrently.
        await asyncio.gather(*(client.send(message) for client in self.clients), return_exceptions=True)

class WebSocketLogHandler(logging.Handler):
    """
    A custom logging handler that sends log records to a LogStreamer.
    """
    def __init__(self, streamer: LogStreamer):
        super().__init__()
        self.streamer = streamer

    def emit(self, record: logging.LogRecord):
        """Formats the log record and broadcasts it via the LogStreamer."""
        log_entry = {"level": record.levelname, "message": self.format(record)}
        asyncio.run_coroutine_threadsafe(self.streamer.broadcast(json.dumps(log_entry)), app.loop)