import asyncio
from app.server import serve_ocpp
import websockets

async def main():
    server_host = "0.0.0.0"
    server_port = 8887
    
    stop_server_event = asyncio.Event()

    async def serve_once(websocket):
        await serve_ocpp(websocket, websocket.path, stop_server_event)

    print(f"Starting OCPP server on ws://{server_host}:{server_port}")

    async with websockets.serve(serve_once, server_host, server_port):
        await stop_server_event.wait()
        
if __name__ == "__main__":
    asyncio.run(main())
