"""
This module serves as the entry point for the OCPP server.
It sets up the centralized logging system and starts the WebSocket server,
delegating each new connection to a dedicated handler.
"""
import asyncio
import logging
from logging import StreamHandler
from functools import partial
import aiohttp
from websockets import serve, ServerProtocol
import uvicorn
from app import web_ui_server
from app.ocpp_handler import OCPPHandler
from app.web_ui_server import app as flask_app
from app.log_streamer import LogStreamer, WebSocketLogHandler
from app.ev_simulator_state import EV_SIMULATOR_STATE

# Configure logging for this module
class ColoredFormatter(logging.Formatter):
    """A custom formatter to add colors to log messages."""
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD_RED = "\033[1;91m"
    RESET = "\033[0m"
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    FORMATS = {
        logging.DEBUG: GREEN + log_format + RESET,
        logging.INFO: BLUE + log_format + RESET,
        logging.WARNING: YELLOW + log_format + RESET,
        logging.ERROR: RED + log_format + RESET,
        logging.CRITICAL: BOLD_RED + log_format + RESET,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.log_format)
        message = record.getMessage()
        if record.levelno == logging.INFO and message.lstrip().startswith("--- Step"):
            log_fmt = self.RED + "%(message)s" + self.RESET
        elif record.levelno == logging.DEBUG and message.lstrip().startswith("------------OCPP Call----------"):
            log_fmt = self.GREEN + "%(message)s" + self.RESET
        return logging.Formatter(log_fmt).format(record)

logger = logging.getLogger(__name__)

async def serve_ocpp_connection(websocket: ServerProtocol):
    """
    The main handler for a new connection. It creates and starts a
    dedicated handler for the charge point.
    """
    # The connection is logged here instead of in a custom protocol class.
    # In websockets v12+, the path is on the `request` attribute.
    path = websocket.request.path
    logger.info(f"Connection received from: {websocket.remote_address} on path '{path}'")
    ocpp_handler = OCPPHandler(websocket, path)
    await ocpp_handler.start()

async def serve_log_stream(websocket: ServerProtocol, streamer: LogStreamer):
    """Handles a single WebSocket connection for log streaming to the UI."""
    await streamer.add_client(websocket)
    try:
        # Keep the connection open and listen for any messages (e.g., a close message)
        # This loop will exit when the client disconnects.
        async for message in websocket:
            # We don't expect messages from the client, but this keeps the connection alive.
            pass
    finally:
        streamer.remove_client(websocket)

async def start_log_server(handler, host, port):
    """A wrapper to run the log server as a background task."""
    async with serve(handler, host, port):
        await asyncio.Future()  # run forever

async def start_http_server():
    """Starts the Flask web server using uvicorn."""
    # The 'interface="wsgi"' parameter tells Uvicorn to use its WSGI-to-ASGI
    # compatibility middleware for the Flask app.
    config = uvicorn.Config(flask_app, host="0.0.0.0", port=5000, log_level="info", interface="wsgi")
    server = uvicorn.Server(config)
    logger.info("Web server is running and listening on 0.0.0.0:5000")
    await server.serve()

async def wait_for_ev_simulator():
    """Waits until a successful connection to the EV simulator is made."""
    url = "http://192.168.0.81/api/status"
    logger.info("Waiting for EV simulator to become available...")
    while True:
        try:
            # Use a short timeout to avoid long waits on each attempt
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        logger.info("EV simulator is available. Starting servers.")
                        return # Success
                    else:
                        logger.debug(f"EV simulator is reachable but returned status {response.status}. Retrying...")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            # Log the specific error type for better diagnostics.
            logger.debug(f"EV simulator not yet available ({type(e).__name__}). Retrying in 5 seconds...")
        await asyncio.sleep(5)

async def poll_ev_simulator_status():
    """Periodically polls the EV simulator's status endpoint."""
    # The IP address of the EV simulator.
    url = "http://192.168.0.81/api/status"
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        status = await response.json()
                        EV_SIMULATOR_STATE.update(status)
                    else:
                        EV_SIMULATOR_STATE.clear() # Clear state if simulator is not reachable
                        logger.debug(f"EV simulator status endpoint returned: {response.status}")
        except aiohttp.ClientConnectorError:
            EV_SIMULATOR_STATE.clear() # Clear state on connection error
            logger.debug("Could not connect to the EV simulator.")
        await asyncio.sleep(5) # Poll every 5 seconds

async def main():
    # Centralized Logging Configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    console_handler = StreamHandler()
    console_handler.setFormatter(ColoredFormatter())
    root_logger.addHandler(console_handler)

    # Before starting any servers, ensure the EV simulator is reachable.
    await wait_for_ev_simulator()

    # --- Log Streaming Setup ---
    log_streamer = LogStreamer()
    # Create a simple formatter for the logs that will be sent over WebSocket.
    # We don't want the ANSI color codes in the JSON payload.
    ws_log_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    ws_log_handler = WebSocketLogHandler(log_streamer)
    ws_log_handler.setFormatter(ws_log_formatter)
    root_logger.addHandler(ws_log_handler)

    logging.getLogger("websockets").setLevel(logging.INFO)

    # Create background tasks for the HTTP and Log Streaming servers
    http_server_task = asyncio.create_task(start_http_server())
    ev_poller_task = asyncio.create_task(poll_ev_simulator_status())

    log_ws_host = "0.0.0.0"
    log_ws_port = 5001 # A different port for the UI logs
    log_stream_handler_with_context = partial(serve_log_stream, streamer=log_streamer)
    log_server_task = asyncio.create_task(start_log_server(log_stream_handler_with_context, log_ws_host, log_ws_port))

    # Start the main OCPP WebSocket server
    ws_server_host = "0.0.0.0"
    ws_server_port = 8887
    flask_app.loop = asyncio.get_running_loop()  # Make the main event loop accessible to the Flask app

    # The `serve` context manager runs the OCPP server and handles its shutdown.
    async with serve(serve_ocpp_connection, ws_server_host, ws_server_port):
        logger.info(f"OCPP WebSocket server created and listening on ({ws_server_host}, {ws_server_port})")
        logger.info(f"Log streaming WebSocket server listening on ({log_ws_host}, {log_ws_port})")
        logger.info("All servers are now running. Press CTRL+C to shut down.")
        try:
            # Keep the main coroutine alive to let the background servers run.
            await asyncio.Future()
        except asyncio.CancelledError:
            # This is the expected result of a CTRL+C, so we can proceed to shutdown.
            logger.info("Shutdown signal received.")
        finally:
            logger.info("Shutting down background services...")
            http_server_task.cancel()
            ev_poller_task.cancel()
            log_server_task.cancel()
        
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated cleanly.")