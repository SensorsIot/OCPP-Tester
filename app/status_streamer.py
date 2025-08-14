"""
EVStatusStreamer: Manages WebSocket clients for streaming EV simulator status.
"""
import asyncio
import json
import logging
from typing import Set, Dict, Any

from websockets.server import ServerConnection
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


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

    async def broadcast_status(self, status: Dict[str, Any]):
        """Broadcasts the EV status as a JSON string to all connected clients."""
        if not self.clients:
            return

        wrapped_message = {
            "type": "ev_status",
            "data": status
        }
        message = json.dumps(wrapped_message)
        logger.debug(f"Broadcasting EV status message: {message}")
        clients_to_send = list(self.clients)
        tasks = [client.send(message) for client in clients_to_send]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for client, result in zip(clients_to_send, results):
            if isinstance(result, ConnectionClosed):
                self.clients.discard(client)
                logger.info(f"Removed disconnected EV status stream client: {client.remote_address}")