"""
Entry point for the OCPP server.

- Centralized logging with colored console + websocket log sink
- Single WebSocket server with path routing:
    /logs        -> UI log stream
    /ev-status   -> UI EV status stream
    /{cpid}      -> OCPP connection for charge point `cpid`
- Flask (via uvicorn) HTTP server for the web UI + REST API
- EV simulator connection wait + periodic status polling with backoff

Erata:
    - 2025-08-24: Modified `run_a5_trigger_message_test` to request a `StatusNotification` instead of a `Heartbeat`.
"""

import asyncio
import logging
import signal
from logging import StreamHandler

import uvicorn
from websockets import serve
from websockets.server import ServerConnection

from app import web_ui_server
from app.ocpp_handler import OCPPHandler
from app.streamers import LogStreamer, WebSocketLogHandler, EVStatusStreamer

from app.core import SERVER_SETTINGS, get_shutdown_event, set_shutdown_event
from app.ev_simulator_manager import EVSimulatorManager
import uvicorn
import aiohttp # NEW
from websockets.server import serve
from app.core import OCPP_HOST, OCPP_PORT, HTTP_HOST, HTTP_PORT, LOG_WS_PATH, EV_STATUS_WS_PATH, EV_SIMULATOR_BASE_URL, EV_STATUS_POLL_INTERVAL
from app.ocpp_server_logic import OcppServerLogic

from app.web_ui_server import app as flask_app, attach_loop, attach_ev_status_streamer




# ---------- Colored logging formatter ----------
class ColoredFormatter(logging.Formatter):
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

# ---------- Per-path WebSocket handlers ----------
async def handle_ocpp(websocket: ServerConnection, path: str, refresh_trigger: asyncio.Event, ev_sim_manager: EVSimulatorManager):
    """Handle OCPP charge point connection on /{charge_point_id}."""
    charge_point_id = path.strip("/")
    logger.info(f"Connection received from {websocket.remote_address} on path '{path}'")

    if not charge_point_id or charge_point_id in (LOG_WS_PATH.strip("/"), EV_STATUS_WS_PATH.strip("/")):
        logger.warning("Invalid OCPP path. Closing connection.")
        await websocket.close()
        return

    handler = OCPPHandler(websocket, path, refresh_trigger, ev_sim_manager)
    await handler.start()

async def handle_log_stream(websocket: ServerConnection, streamer: LogStreamer):
    await streamer.add_client(websocket)
    try:
        async for _ in websocket:
            pass
    finally:
        streamer.remove_client(websocket)

async def handle_ev_status_stream(websocket: ServerConnection, streamer: EVStatusStreamer):
    await streamer.add_client(websocket)
    try:
        async for _ in websocket:
            pass
    finally:
        streamer.remove_client(websocket)

async def ws_router(websocket: ServerConnection,
                    log_streamer: LogStreamer, ev_status_streamer: EVStatusStreamer,
                    ev_refresh_trigger: asyncio.Event, ev_sim_manager: EVSimulatorManager):
    """Route incoming WS connections based on the request path."""
    path = "unknown"
    try:
        path = websocket.path
        if path == LOG_WS_PATH:
            await handle_log_stream(websocket, log_streamer)
        elif path == EV_STATUS_WS_PATH:
            await handle_ev_status_stream(websocket, ev_status_streamer)
        else:
            await handle_ocpp(websocket, path, ev_refresh_trigger, ev_sim_manager)
    except Exception as e:
        logger.error(f"WebSocket router error on path '{path}': {e}", exc_info=True)
        try:
            await websocket.close()
        except Exception:
            pass

# ---------- HTTP (Flask) via uvicorn ----------
async def start_http_server():
    config = uvicorn.Config(
        web_ui_server.app,
        host=HTTP_HOST,
        port=HTTP_PORT,
        log_level="warning",
        interface="wsgi",
    )
    server = uvicorn.Server(config)
    logger.info(f"Web server listening on {HTTP_HOST}:{HTTP_PORT}")
    await server.serve()

# ---------- Main ----------
async def main():
    loop = asyncio.get_running_loop()

    # Central logging setup
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    console = StreamHandler()
    console.setFormatter(ColoredFormatter())
    root_logger.addHandler(console)

    # Streamers
    log_streamer = LogStreamer()
    ev_status_streamer = EVStatusStreamer()
    ev_refresh_trigger = asyncio.Event()

    ws_log_handler = WebSocketLogHandler(log_streamer, loop=loop)
    ws_log_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    root_logger.addHandler(ws_log_handler)

    logging.getLogger("websockets").setLevel(logging.INFO)

    # Let Flask know our loop (used by /api/test/*)
    web_ui_server.attach_loop(loop)
    web_ui_server.attach_ev_status_streamer(ev_status_streamer)

    # Instantiate the manager for the EV simulator
    ev_sim_manager = EVSimulatorManager(
        status_streamer=ev_status_streamer,
        refresh_trigger=ev_refresh_trigger
    )

    # Start the HTTP server first so the UI is always available
    http_task = asyncio.create_task(start_http_server())

    logger.info(f"Starting WebSocket server on {OCPP_HOST}:{OCPP_PORT} "
                f"(paths: '{LOG_WS_PATH}', '{EV_STATUS_WS_PATH}', '/<ChargePointId>')")
    ws_server = await serve(
        lambda ws: ws_router(ws, log_streamer, ev_status_streamer, ev_refresh_trigger, ev_sim_manager),
        OCPP_HOST,
        OCPP_PORT,
        ping_interval=None,
        max_size=2**22,
    )

    # Start all background tasks and gather them.
    tasks = [
        http_task,
        asyncio.create_task(ev_sim_manager.start()),
    ]

    # Wait for shutdown event
    await shutdown_event.wait()

    logger.info("Shutdown event received. Closing servers...")

    # Close WebSocket server
    ws_server.close()
    await ws_server.wait_closed()

    # Cancel all running tasks
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True) # Gather to ensure tasks are cancelled

    logger.info("Server shut down gracefully.")

    # Stop the event loop
    loop.stop()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Initialize shutdown event
    shutdown_event = asyncio.Event()
    set_shutdown_event(shutdown_event)

    # Set up signal handler for graceful shutdown
    def handle_sigint(sig, frame):
        logger.info("Ctrl-C (SIGINT) received. Initiating graceful shutdown...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        main_task = loop.create_task(main())
        loop.run_until_complete(main_task)
    finally:
        loop.close()