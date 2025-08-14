"""
Entry point for the OCPP server.

- Centralized logging with colored console + websocket log sink
- Single WebSocket server with path routing:
    /logs        -> UI log stream
    /ev-status   -> UI EV status stream
    /{cpid}      -> OCPP connection for charge point `cpid`
- Flask (via uvicorn) HTTP server for the web UI + REST API
- EV simulator connection wait + periodic status polling with backoff
"""

import asyncio
import logging
from logging import StreamHandler

import aiohttp
import uvicorn
from websockets import serve
from websockets.server import ServerConnection

from app import web_ui_server
from app.ocpp_handler import OCPPHandler
from app.log_streamer import LogStreamer, WebSocketLogHandler
from app.state import EV_SIMULATOR_STATE
from app.status_streamer import EVStatusStreamer
from app.config import (
    OCPP_HOST, OCPP_PORT,
    HTTP_HOST, HTTP_PORT,
    LOG_WS_PATH, EV_STATUS_WS_PATH,
    EV_SIMULATOR_BASE_URL, EV_STATUS_POLL_INTERVAL, EV_WAIT_MAX_BACKOFF,
)

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
async def handle_ocpp(websocket: ServerConnection, path: str, refresh_trigger: asyncio.Event):
    """Handle OCPP charge point connection on /{charge_point_id}."""
    charge_point_id = path.strip("/")
    logger.info(f"Connection received from {websocket.remote_address} on path '{path}'")

    if not charge_point_id or charge_point_id in (LOG_WS_PATH.strip("/"), EV_STATUS_WS_PATH.strip("/")):
        logger.warning("Invalid OCPP path. Closing connection.")
        await websocket.close()
        return

    handler = OCPPHandler(websocket, path, refresh_trigger)
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
                    ev_refresh_trigger: asyncio.Event):
    """Route incoming WS connections based on the request path."""
    path = "unknown"
    try:
        path = websocket.request.path
        if path == LOG_WS_PATH:
            await handle_log_stream(websocket, log_streamer)
        elif path == EV_STATUS_WS_PATH:
            await handle_ev_status_stream(websocket, ev_status_streamer)
        else:
            await handle_ocpp(websocket, path, ev_refresh_trigger)
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
        log_level="info",
        interface="wsgi",
    )
    server = uvicorn.Server(config)
    logger.info(f"Web server listening on {HTTP_HOST}:{HTTP_PORT}")
    await server.serve()

# ---------- EV simulator wait + polling ----------
async def wait_for_ev_simulator():
    url = f"{EV_SIMULATOR_BASE_URL}/api/status"
    backoff = 1
    logger.info(f"Waiting for EV simulator at {url} ...")
    while True:
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        logger.info("EV simulator is available. Starting servers.")
                        return
                    logger.debug(f"EV simulator reachable but status {resp.status}. Retrying...")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug(f"EV simulator not available ({type(e).__name__}). Backing off {backoff}s...")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, EV_WAIT_MAX_BACKOFF)

async def poll_ev_simulator_status(ev_status_streamer: EVStatusStreamer,
                                   refresh_trigger: asyncio.Event):
    url = f"{EV_SIMULATOR_BASE_URL}/api/status"
    backoff = EV_STATUS_POLL_INTERVAL
    while True:
        try:
            logger.debug("Polling EV simulator for status...")
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.debug(f"Polled EV status: {data}")
                        EV_SIMULATOR_STATE.update(data)
                        await ev_status_streamer.broadcast_status(EV_SIMULATOR_STATE)
                        backoff = EV_STATUS_POLL_INTERVAL
                    else:
                        EV_SIMULATOR_STATE.clear()
                        logger.debug("EV simulator status endpoint was not OK, clearing state.")
                        await ev_status_streamer.broadcast_status({})
                        logger.debug(f"EV status endpoint returned {resp.status}")
        except aiohttp.ClientError:
            EV_SIMULATOR_STATE.clear()
            await ev_status_streamer.broadcast_status({})
            logger.debug("Could not connect to EV simulator.")
            backoff = min(max(backoff * 2, EV_STATUS_POLL_INTERVAL), 60)
        except Exception as e:
            logger.error(f"Polling EV simulator failed: {e}", exc_info=True)

        try:
            # Wait for either the poll interval to pass or an explicit trigger
            sleep_task = asyncio.create_task(asyncio.sleep(backoff))
            trigger_task = asyncio.create_task(refresh_trigger.wait())

            done, pending = await asyncio.wait(
                {sleep_task, trigger_task},
                return_when=asyncio.FIRST_COMPLETED
            )

            if trigger_task in done:
                logger.debug("EV status poll triggered by an event.")
                refresh_trigger.clear()

            for task in pending:
                task.cancel()
        except asyncio.CancelledError:
            break

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

    await wait_for_ev_simulator()

    logger.info(f"Starting WebSocket server on {OCPP_HOST}:{OCPP_PORT} "
                f"(paths: '{LOG_WS_PATH}', '{EV_STATUS_WS_PATH}', '/<ChargePointId>')")
    ws_server = await serve(
        lambda ws: ws_router(ws, log_streamer, ev_status_streamer, ev_refresh_trigger),
        OCPP_HOST,
        OCPP_PORT,
        ping_interval=None,
        max_size=2**22,
    )

    tasks = [
        asyncio.create_task(start_http_server()),
        asyncio.create_task(poll_ev_simulator_status(ev_status_streamer, ev_refresh_trigger)),
    ]

    try:
        await asyncio.gather(*tasks)
    finally:
        ws_server.close()
        await ws_server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
