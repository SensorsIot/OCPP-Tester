import asyncio
from app.server import serve_ocpp
import websockets
from websockets.legacy.server import WebSocketServerProtocol, WebSocketServer
import logging

# Configure logging for this module
# Set level to DEBUG to see more details from the websockets library itself.
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OcppProtocol(WebSocketServerProtocol):
    """
    A custom WebSocket protocol class to ensure the connection path is
    reliably passed to the OCPP handler. It also adds connection logging.
    """
    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        logger.info(f"Connection received from: {peername}")
        super().connection_made(transport)

    def connection_lost(self, exc):
        logger.info(f"Connection lost. Exception: {exc}")
        super().connection_lost(exc)

async def main():
    server_host = "0.0.0.0"
    server_port = 8887

    print(f"Starting OCPP server on ws://{server_host}:{server_port}")
    logger.info(f"Attempting to start server on {server_host}:{server_port}")

    # Replicating the logic from `websockets.serve` to build the server manually.
    # This provides more control and helps debug connection issues.
    loop = asyncio.get_running_loop()

    # 1. The WebSocketServer manages the connections.
    ws_server = WebSocketServer()

    # 2. The protocol_factory is a callable that returns a new protocol instance.
    #    We now pass `serve_ocpp` as the ws_handler. The base protocol will
    #    call this after a successful handshake.
    protocol_factory = lambda: OcppProtocol(ws_handler=serve_ocpp, ws_server=ws_server)

    try:
        server = await loop.create_server(
            protocol_factory,
            host=server_host,
            port=server_port,
        )
        # This is the crucial step: we must associate the asyncio server
        # with the WebSocketServer instance. This completes the setup that
        # `websockets.serve()` would normally do automatically.
        ws_server.server = server
        logger.info(f"Server created and listening on {server.sockets[0].getsockname()}")
    except Exception as e:
        logger.error(f"Failed to create server: {e}", exc_info=True)
        return
    
    try:
        # The server is now running in the background.
        # We wait indefinitely until the program is stopped (e.g., by Ctrl+C).
        await asyncio.Future()  # Run forever
    finally:
        # This block will run when the server is shutting down.
        print("\n-------------------------E N D --------------------------------")
        logger.info("Server has been shut down.")
        
if __name__ == "__main__":
    asyncio.run(main())
