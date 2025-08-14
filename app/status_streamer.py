"""
Minimal EV status streamer for UI via WebSocket.
"""
import json
import logging
from typing import Set, Dict, Any
from websockets.server import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK, ConnectionClosedError

logger = logging.getLogger(__name__)

class EVStatusStreamer:
    def __init__(self):
        self.clients: Set[WebSocketServerProtocol] = set()

    async def add_client(self, websocket: WebSocketServerProtocol):
        logger.info(f"EV status client connected: {websocket.remote_address}")
        self.clients.add(websocket)

    def remove_client(self, websocket: WebSocketServerProtocol):
        logger.info(f"EV status client disconnected: {websocket.remote_address}")
        self.clients.discard(websocket)

    async def broadcast_status(self, status: Dict[str, Any]):
        if not self.clients:
            return
        payload = json.dumps({"type": "ev_status", "data": status})
        dead = []
        for client in list(self.clients):
            try:
                await client.send(payload)
            except (ConnectionClosed, ConnectionClosedOK, ConnectionClosedError):
                dead.append(client)
            except Exception:
                dead.append(client)
        for d in dead:
            self.clients.discard(d)
