"""
Contains classes for streaming logs and EV status over WebSockets.
"""
import asyncio
import json
import logging
from typing import Set, Dict, Any

from websockets.server import ServerConnection
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class LogStreamer:
    """Manages a set of WebSocket clients for log streaming."""

    def __init__(self):
        self.clients: Set[ServerConnection] = set()

    async def add_client(self, websocket: ServerConnection):
        """Adds a new client to the set of log stream subscribers."""
        self.clients.add(websocket)
        logger.info(f"Log stream client connected: {websocket.remote_address}")

    def remove_client(self, websocket: ServerConnection):
        """Removes a client from the set."""
        self.clients.discard(websocket)
        logger.info(f"Log stream client disconnected: {websocket.remote_address}")

    async def close_all_clients(self):
        """Closes all connected clients during shutdown."""
        clients_to_close = list(self.clients)
        for client in clients_to_close:
            try:
                await client.close()
            except Exception as e:
                logger.debug(f"Error closing log stream client: {e}")
        self.clients.clear()

    async def broadcast(self, message: str):
        """Broadcasts a log message to all connected clients."""
        if not self.clients:
            return

        clients_to_send = list(self.clients)
        tasks = [client.send(message) for client in clients_to_send]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for client, result in zip(clients_to_send, results):
            if isinstance(result, ConnectionClosed):
                self.clients.discard(client)
                logger.info(f"Removed disconnected log stream client: {client.remote_address}")


class WebSocketLogHandler(logging.Handler):
    """A logging handler that sends records to a WebSocket streamer."""

    def __init__(self, streamer: LogStreamer, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.streamer = streamer
        self.loop = loop

    def emit(self, record: logging.LogRecord):
        """Formats and sends a log record to the streamer."""
        try:
            if self.loop.is_closed() or not self.streamer.clients:
                return
            msg = {
                "levelname": record.levelname,
                "message": self.format(record)
            }
            # Only create task if loop is running and not shutting down
            if self.loop.is_running():
                self.loop.call_soon_threadsafe(self._safe_broadcast, json.dumps(msg))
        except Exception:
            # Silently ignore errors during shutdown
            pass

    def _safe_broadcast(self, message: str):
        """Safely creates a broadcast task if the loop is still running."""
        try:
            if not self.loop.is_closed() and self.loop.is_running():
                self.loop.create_task(self.streamer.broadcast(message))
        except Exception:
            # Ignore errors during shutdown
            pass


class EVStatusStreamer:
    """Manages a set of WebSocket clients for EV status streaming."""

    def __init__(self):
        self.clients: Set[ServerConnection] = set()

    async def add_client(self, websocket: ServerConnection):
        """Adds a new client to the set of EV status subscribers."""
        self.clients.add(websocket)
        logger.info(f"EV status stream client connected: {websocket.remote_address}")

    def remove_client(self, websocket: ServerConnection):
        """Removes a client from the set."""
        self.clients.discard(websocket)
        logger.info(f"EV status stream client disconnected: {websocket.remote_address}")

    async def close_all_clients(self):
        """Closes all connected clients during shutdown."""
        clients_to_close = list(self.clients)
        for client in clients_to_close:
            try:
                await client.close()
            except Exception as e:
                logger.debug(f"Error closing EV status stream client: {e}")
        self.clients.clear()

    async def broadcast_status(self, status: Dict[str, Any]):
        """Broadcasts the EV status as a JSON string to all connected clients."""
        if not self.clients:
            return

        wrapped_message = {
            "type": "ev_status",
            "data": status
        }
        message = json.dumps(wrapped_message)
        clients_to_send = list(self.clients)
        tasks = [client.send(message) for client in clients_to_send]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for client, result in zip(clients_to_send, results):
            if isinstance(result, ConnectionClosed):
                self.clients.discard(client)
                logger.info(f"Removed disconnected EV status stream client: {client.remote_address}")
