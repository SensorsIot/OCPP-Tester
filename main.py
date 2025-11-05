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

Post-Reset Handling (E.9 Brutal Stop aftermath):
    - Accept StopTransaction(s) with reasons like "HardReset" / "PowerLoss"
    - If some vendors don't send StopTransaction after reset, treat those transactions as implicitly closed on reconnect
    - Clean CSMS state appropriately
    - (Optional) Send ChangeAvailability(Unavailable) per connector to block new sessions while reconciling state, then flip back to Operative
"""

import argparse
import asyncio
import logging
import signal
import warnings
from logging import StreamHandler, FileHandler
from logging.handlers import RotatingFileHandler
import os

import uvicorn
from websockets import serve
from websockets.server import ServerConnection

from app import web_ui_server
from app.ocpp_handler import OCPPHandler
from app.streamers import LogStreamer, WebSocketLogHandler, EVStatusStreamer

from app.core import SERVER_SETTINGS, get_shutdown_event, set_shutdown_event
SERVER_SETTINGS["auto_detection_completed"] = False
from app.ev_simulator_manager import EVSimulatorManager
import uvicorn
import aiohttp # NEW
from websockets.server import serve
from app.core import OCPP_HOST, OCPP_PORT, HTTP_HOST, HTTP_PORT, LOG_WS_PATH, EV_STATUS_WS_PATH, EV_SIMULATOR_BASE_URL, EV_STATUS_POLL_INTERVAL
from app.ocpp_server_logic import OcppServerLogic

from app.web_ui_server import app as flask_app, attach_loop, attach_ev_status_streamer




import re


# ---------- Colored logging formatter ----------
class ColoredFormatter(logging.Formatter):
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD_RED = "\033[1;91m"
    PURPLE = "\033[95m"
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
        elif record.levelno == logging.DEBUG and "OCPP Call" in message:
            log_fmt = self.GREEN + "%(message)s" + self.RESET

        formatter = logging.Formatter(log_fmt)
        formatted_message = formatter.format(record)

        # Apply purple color to transaction IDs
        transaction_id_patterns = [
            (r"(CP Transaction ID: )(\d+)", f"\1{self.PURPLE}\2{self.RESET}"),
            (r"(transactionId=)(\d+)", f"\1{self.PURPLE}\2{self.RESET}"),
            (r"(transaction id )(\d+)", f"\1{self.PURPLE}\2{self.RESET}"),
            (r"(transaction )(\d+)\b", f"\1{self.PURPLE}\2{self.RESET}"), # General with word boundary
            (r"(Transaction ID: )(\d+)", f"\1{self.PURPLE}\2{self.RESET}"),
            (r"(transactionId: )(\d+)", f"\1{self.PURPLE}\2{self.RESET}"),
            (r"(CP ID: )(\d+)", f"\1{self.PURPLE}\2{self.RESET}"),
            (r"(CS Internal ID: )(\d+)", f"\1{self.PURPLE}\2{self.RESET}"),
        ]

        for pattern, replacement in transaction_id_patterns:
            formatted_message = re.sub(pattern, replacement, formatted_message)

        if ("Received" in message or "Failed to parse" in message or "Unknown OCPP message type" in message):
            return f"*** {formatted_message}"
        elif "Sent " in message and ("Payload:" in message or "Waiting..." in message or "Sent response for" in message):
            return f"---- {formatted_message}"
        else:
            return formatted_message

logger = logging.getLogger(__name__)

# ---------- File logging formatter for disk logging ----------
class FileLogFormatter(logging.Formatter):
    def __init__(self):
        super().__init__("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    def format(self, record):
        # Strip ANSI color codes from the message for clean file logging
        import re
        message = record.getMessage()
        # Remove ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_message = ansi_escape.sub('', message)

        # Create a copy of the record with cleaned message
        record_copy = logging.makeLogRecord(record.__dict__)
        record_copy.msg = clean_message
        record_copy.args = None

        return super().format(record_copy)

# ---------- Per-path WebSocket handlers ----------
async def handle_ocpp(websocket: ServerConnection, path: str, refresh_trigger: asyncio.Event, ev_sim_manager: EVSimulatorManager):
    """Handle OCPP charge point connection on /{charge_point_id}."""
    from datetime import datetime, timezone
    from app.core import register_discovered_charge_point, unregister_charge_point

    charge_point_id = path.strip("/")
    logger.info(f"🔌 OCPP connection received from {websocket.remote_address} on path '{path}'")
    logger.debug(f"🔍 Extracted charge_point_id: '{charge_point_id}'")

    if not charge_point_id or charge_point_id in (LOG_WS_PATH.strip("/"), EV_STATUS_WS_PATH.strip("/")):
        logger.warning(f"❌ Invalid OCPP path '{path}' or conflicts with reserved paths. Closing connection.")
        logger.warning(f"🔍 LOG_WS_PATH.strip('/'): '{LOG_WS_PATH.strip('/')}'")
        logger.warning(f"🔍 EV_STATUS_WS_PATH.strip('/'): '{EV_STATUS_WS_PATH.strip('/')}'")
        await websocket.close()
        return

    # Register the discovered charge point
    connection_info = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "remote_address": str(websocket.remote_address)
    }
    auto_selected = register_discovered_charge_point(charge_point_id, connection_info)

    if auto_selected:
        logger.info(f"🎯 AUTODISCOVERY: '{charge_point_id}' is now the active charge point")
    else:
        logger.info(f"📋 DISCOVERY: Registered charge point '{charge_point_id}' (not auto-selected)")

    logger.debug(f"✅ Valid charge point ID '{charge_point_id}'. Creating OCPP handler...")
    handler = OCPPHandler(websocket, path, refresh_trigger, ev_sim_manager)
    logger.debug(f"🚀 Starting OCPP handler for charge point '{charge_point_id}'...")

    try:
        await handler.start()
    finally:
        # Unregister when connection closes
        unregister_charge_point(charge_point_id)
        logger.info(f"🔌 Charge point '{charge_point_id}' disconnected and unregistered")

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
        logger.debug(f"🔍 WebSocket connection attempt from {websocket.remote_address} on path: '{path}'")
        logger.debug(f"🔍 LOG_WS_PATH='{LOG_WS_PATH}', EV_STATUS_WS_PATH='{EV_STATUS_WS_PATH}'")

        if path == LOG_WS_PATH:
            logger.debug(f"🔍 Routing to log stream handler")
            await handle_log_stream(websocket, log_streamer)
        elif path == EV_STATUS_WS_PATH:
            logger.debug(f"🔍 Routing to EV status stream handler")
            await handle_ev_status_stream(websocket, ev_status_streamer)
        else:
            logger.debug(f"🔍 Routing to OCPP handler for charge point path: '{path}'")
            await handle_ocpp(websocket, path, ev_refresh_trigger, ev_sim_manager)
    except Exception as e:
        logger.error(f"❌ WebSocket router error on path '{path}': {e}", exc_info=True)
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

    # Store server instance globally for shutdown
    global http_server_instance
    http_server_instance = server

    logger.info(f"Web server listening on {HTTP_HOST}:{HTTP_PORT}")

    try:
        await server.serve()
    except asyncio.CancelledError:
        logger.info("HTTP server task cancelled, shutting down...")
        # More graceful shutdown
        if hasattr(server, 'should_exit'):
            server.should_exit = True
        if hasattr(server, 'force_exit'):
            server.force_exit = True
        # Don't re-raise to avoid error messages
        return
    except Exception as e:
        # During shutdown, ASGI applications may throw various cancellation errors
        if "CancelledError" in str(e) or "cancelled" in str(e).lower():
            logger.info("HTTP server cancelled during shutdown")
        else:
            logger.error(f"HTTP server error: {e}")
        return

# ---------- Main ----------
async def main():
    loop = asyncio.get_running_loop()

    # Central logging setup
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Console handler with colors
    console = StreamHandler()
    console.setFormatter(ColoredFormatter())
    root_logger.addHandler(console)

    # Disk logging setup - create logs directory if it doesn't exist
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    # File handler with rotation (10MB max file size, keep 5 backup files)
    file_handler = RotatingFileHandler(
        os.path.join(logs_dir, "ocpp_commands.log"),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(FileLogFormatter())
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    logger.info(f"📁 Command logging enabled - logs saved to {os.path.join(logs_dir, 'ocpp_commands.log')}")

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

    logger.info(f"🚀 Starting WebSocket server on {OCPP_HOST}:{OCPP_PORT} "
                f"(paths: '{LOG_WS_PATH}', '{EV_STATUS_WS_PATH}', '/<ChargePointId>')")
    logger.info(f"🌐 WebSocket server will accept connections at ws://{OCPP_HOST}:{OCPP_PORT}/<charge_point_id>")
    logger.info(f"🖥️  Web UI available at http://{HTTP_HOST}:{HTTP_PORT}")
    logger.info(f"📡 To connect a charge point, use: ws://{OCPP_HOST}:{OCPP_PORT}/YourChargePointID")

    # Log network interface information
    try:
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        logger.info(f"🌍 Server hostname: {hostname}")
        logger.info(f"🔗 Server local IP: {local_ip}")
        logger.info(f"📍 Listening on all interfaces (0.0.0.0) - accessible from network")
    except Exception as e:
        logger.warning(f"Could not determine network info: {e}")
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

    # Signal HTTP server to shutdown gracefully
    if 'http_server_instance' in globals():
        try:
            http_server_instance.should_exit = True
            if hasattr(http_server_instance, 'force_exit'):
                http_server_instance.force_exit = True
            logger.info("HTTP server shutdown signal sent")
            # Give HTTP server a moment to start shutting down
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"Error signaling HTTP server shutdown: {e}")

    # Close WebSocket server
    ws_server.close()

    # Wait for WebSocket server to close with timeout
    try:
        await asyncio.wait_for(ws_server.wait_closed(), timeout=5.0)
        logger.info("WebSocket server closed successfully")
    except asyncio.TimeoutError:
        logger.warning("WebSocket server close timed out after 5 seconds")

    # Cancel all running tasks (both tracked and untracked)
    all_tasks = [t for t in asyncio.all_tasks() if not t.done()]
    logger.info(f"Cancelling {len(all_tasks)} pending tasks...")

    for task in all_tasks:
        if not task.done():
            task.cancel()

    # Wait for all tasks to complete with shorter timeout to avoid hanging
    if all_tasks:
        try:
            # Suppress CancelledError and other expected exceptions during shutdown
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                warnings.simplefilter("ignore", asyncio.CancelledError)
                # Use wait() instead of wait_for() to avoid timeout cancellation issues
                done, pending = await asyncio.wait(
                    all_tasks,
                    timeout=2.0,
                    return_when=asyncio.ALL_COMPLETED
                )
                if pending:
                    logger.info(f"Task cancellation completed ({len(pending)} tasks still pending, this is normal)")
                else:
                    logger.info("All tasks cancelled successfully")
        except (asyncio.CancelledError, Exception):
            # Ignore all exceptions during shutdown - they're expected
            logger.info("Task cancellation completed")
    else:
        logger.info("No pending tasks to cancel")

    # Close EV simulator manager if it exists
    try:
        await ev_sim_manager.stop()
    except Exception as e:
        logger.warning(f"Error stopping EV simulator manager: {e}")

    # Close all streamer clients
    try:
        await log_streamer.close_all_clients()
        await ev_status_streamer.close_all_clients()
        logger.info("All streamer clients closed")
    except Exception as e:
        logger.warning(f"Error closing streamers: {e}")

    # Final cleanup - ensure no tasks are left
    final_tasks = [t for t in asyncio.all_tasks() if not t.done()]
    if final_tasks:
        logger.info(f"Force cancelling {len(final_tasks)} remaining tasks")
        for task in final_tasks:
            task.cancel()
        # Give them a moment to cancel, but don't wait if we're one of the tasks being cancelled
        try:
            # Only wait if we're not being cancelled ourselves
            current_task = asyncio.current_task()
            if current_task not in final_tasks:
                await asyncio.wait(final_tasks, timeout=1.0)
        except Exception:
            # Ignore any exceptions during final cleanup
            pass

    logger.info("Server shut down gracefully.")

    # Stop the event loop
    loop.stop()

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="OCPP Server with auto-detection")
    parser.add_argument("--unit", choices=["W", "A"],
                       help="Override charging rate unit (W=Watts, A=Amperes). If not specified, auto-detection will be attempted.")
    args = parser.parse_args()

    # Set override unit if specified
    if args.unit:
        from app.core import SERVER_SETTINGS
        SERVER_SETTINGS["charging_rate_unit"] = args.unit
        SERVER_SETTINGS["charging_rate_unit_auto_detected"] = False
        SERVER_SETTINGS["auto_detection_completed"] = True

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Initialize shutdown event
    shutdown_event = asyncio.Event()
    set_shutdown_event(shutdown_event)

    # Track if shutdown has been initiated using a class to avoid nonlocal issues
    class ShutdownState:
        initiated = False
        count = 0

    # Set up signal handler for graceful shutdown
    def handle_sigint(sig, frame):
        ShutdownState.count += 1

        if not ShutdownState.initiated:
            ShutdownState.initiated = True
            logger.info("Ctrl-C (SIGINT) received. Initiating graceful shutdown...")
            shutdown_event.set()
        elif ShutdownState.count == 2:
            logger.info("Second Ctrl-C received. Please wait for graceful shutdown...")
        elif ShutdownState.count >= 3:
            logger.warning("Multiple interrupts received. Forcing immediate exit...")
            import os
            os._exit(1)

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        main_task = loop.create_task(main())
        loop.run_until_complete(main_task)
    finally:
        loop.close()