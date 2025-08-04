# -*- coding: utf-8 -*-
"""
This is the main entry point for the OCPP server application.
It starts a WebSocket server to listen for connections from a Wallbox.
"""
import asyncio
from ocpp.server import serve_ocpp # Import the server handler
from websockets.server import serve as websockets_serve

async def main():
    """
    The main entry point for the application.
    It starts the server task to listen for Wallbox connections.
    """
    server_host = "0.0.0.0"
    server_port = 8887
    
    # Start the server task (our program listening for connections from a Wallbox)
    async with websockets_serve(serve_ocpp, server_host, server_port):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
