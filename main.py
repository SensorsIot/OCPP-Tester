# -*- coding: utf-8 -*-
"""
This is the main entry point for the OCPP server application.
It starts a WebSocket server to listen for connections from a Wallbox,
and is configured to shut down after the first connection closes.
"""
import asyncio
from websockets.server import serve as websockets_serve
from app.server import serve_ocpp

async def main():
    """
    The main entry point for the application.
    It starts the server task to listen for a single Wallbox connection
    and stops once that connection is closed.
    """
    server_host = "0.0.0.0"
    server_port = 8887
    
    # An event to signal when the server should stop.
    # This will be set by the connection handler after the first client disconnects.
    stop_server_event = asyncio.Event()

    async def serve_once(websocket, path):
        """
        A wrapper around serve_ocpp to handle a single connection and then
        signal for the server to shut down.
        """
        await serve_ocpp(websocket, path, stop_server_event)

    print(f"Starting OCPP server on ws://{server_host}:{server_port}")
    # Start the server and wait for the stop_server_event to be set.
    # The 'serve' function will gracefully stop accepting new connections
    # and wait for existing ones to close when the context manager exits.
    async with websockets_serve(serve_once, server_host, server_port):
        await stop_server_event.wait()

if __name__ == "__main__":
    asyncio.run(main())
