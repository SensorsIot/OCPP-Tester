"""
LogStreamer: Manages WebSocket clients for streaming logs.
WebSocketLogHandler: A logging.Handler to sink logs to the streamer.
"""
import asyncio
import logging
from typing import Set

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
            msg = self.format(record)
            asyncio.run_coroutine_threadsafe(self.streamer.broadcast(msg), self.loop)
        except Exception:
            self.handleError(record)