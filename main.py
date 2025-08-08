import asyncio
from app.server import serve_ocpp
import websockets
from websockets.legacy.server import WebSocketServerProtocol, WebSocketServer
import logging
from logging import StreamHandler

# Configure logging for this module
# Set level to DEBUG to see more details from the websockets library itself.

class ColoredFormatter(logging.Formatter):
    """A custom formatter to add colors to log messages."""
    # ANSI color codes
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD_RED = "\033[1;91m"
    RESET = "\033[0m"
    
    # Define formats for each log level
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    FORMATS = {
        logging.DEBUG: GREEN + log_format + RESET,
        logging.INFO: BLUE + log_format + RESET,
        logging.WARNING: YELLOW + log_format + RESET,
        logging.ERROR: RED + log_format + RESET,
        logging.CRITICAL: BOLD_RED + log_format + RESET,
    }

    def format(self, record):
        # Get the format string for the record's level
        log_fmt = self.FORMATS.get(record.levelno, self.log_format)
        message = record.getMessage()
        
        # Special override for step announcements to make them stand out in red.
        if record.levelno == logging.INFO and message.lstrip().startswith("--- Step"):
            # For step titles, we only want to print the message itself, without the other log metadata.
            log_fmt = self.RED + "%(message)s" + self.RESET
        
        # Special override for OCPP call separators to make them stand out.
        elif record.levelno == logging.DEBUG and message.lstrip().startswith("------------OCPP Call----------"):
            # For separators, we only want to print the message itself, without the other log metadata.
            log_fmt = self.GREEN + "%(message)s" + self.RESET
            
        return logging.Formatter(log_fmt).format(record)

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
    # --- Centralized Logging Configuration ---
    # Get the root logger, which is the parent of all other loggers.
    root_logger = logging.getLogger()
    
    # Set the application-wide logging level to DEBUG to see all colored messages.
    root_logger.setLevel(logging.DEBUG)

    # Remove any handlers that may have been added by imported modules.
    # This is important to prevent duplicate logs from multiple basicConfig calls.
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Create a new handler to print to the console (stdout).
    console_handler = StreamHandler()
    # Set our custom formatter on the handler. The formatter itself now contains the format string.
    console_handler.setFormatter(ColoredFormatter())
    # Add the configured handler to the root logger.
    root_logger.addHandler(console_handler)
    # --- End of Logging Configuration ---

    # Set the logging level for the websockets library to INFO to reduce noise.
    logging.getLogger("websockets").setLevel(logging.INFO)

    server_host = "0.0.0.0"
    server_port = 8887

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
        logger.info("Server is now running. Waiting for a Charge Point to connect...")
    except Exception as e:
        logger.error(f"Failed to create server: {e}", exc_info=True)
        return
    
    try:
        # The server is now running in the background.
        # We wait indefinitely until the program is stopped (e.g., by Ctrl+C).
        await asyncio.Future()  # Run forever
    finally:
        # This block will run when the server is shutting down.
        logger.info("\n-------------------------E N D --------------------------------")
        logger.info("Server has been shut down.")
        
if __name__ == "__main__":
    asyncio.run(main())
