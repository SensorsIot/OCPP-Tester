"""
This module contains the `OCPPHandler` class, which manages a single
WebSocket connection to a charge point, handling all incoming messages
and orchestrating server-initiated logic, including the test sequence.
"""
import asyncio
import json
import logging
from dataclasses import asdict, is_dataclass
from typing import Any, Dict
from websockets.server import ServerProtocol
from websockets.exceptions import ConnectionClosedOK

from app.state import CHARGE_POINTS

from app.handlers import MESSAGE_HANDLERS
from app.test_sequence import TestSequence
from app.test_manager import TestManager
from app.messages import (
    BootNotificationRequest,
    AuthorizeRequest,
    DataTransferRequest,
    StatusNotificationRequest,
    FirmwareStatusNotificationRequest,
    DiagnosticsStatusNotificationRequest,
    HeartbeatRequest,
    StartTransactionRequest,
    StopTransactionRequest,
    MeterValuesRequest,
)

logger = logging.getLogger(__name__)

def create_ocpp_message(
    message_type_id: int, unique_id: str, payload: Any, action: str = None
) -> str:
    """
    Creates a JSON-formatted OCPP message array.
    """
    dict_factory = lambda data: {k: v for (k, v) in data if v is not None}
    payload_to_send = asdict(payload, dict_factory=dict_factory) if is_dataclass(payload) else payload
    
    if action:
        message = [message_type_id, unique_id, action, payload_to_send]
    else:
        message = [message_type_id, unique_id, payload_to_send]
        
    logger.debug("\n\n------------OCPP Call----------")
    return json.dumps(message)


class OCPPHandler:
    """
    Manages the lifecycle and communication for a single charge point connection.
    """
    def __init__(self, websocket: ServerProtocol, path: str):
        self.websocket = websocket
        self.charge_point_id = path.strip("/")
        self.logic_task = None
        self.pending_requests: Dict[str, Dict[str, Any]] = {}
        self.test_sequence = TestSequence(
            websocket=self.websocket,
            charge_point_id=self.charge_point_id,
            send_and_wait_callback=self.send_and_wait
        )
        self.test_manager = TestManager(self)

    async def send_and_wait(self, action: str, request_payload: Any, timeout: int = 30):
        """
        A generic function to send a server-initiated request and wait for its response.
        This is now a method of the handler class, as it's specific to the connection.
        """
        unique_id = self.test_sequence.get_unique_id() # Use a method from TestSequence
        event = asyncio.Event()
        self.pending_requests[unique_id] = {"action": action, "event": event}

        message = create_ocpp_message(2, unique_id, request_payload, action)
        await self.websocket.send(message)
        logger.info(f"Sent {action} (id={unique_id}). Waiting for response...")

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            logger.info(f"Response received for {action} (id={unique_id}). Proceeding.")
        except asyncio.TimeoutError:
            logger.error(f"Timeout: No response for {action} (id={unique_id}) within {timeout}s.")
            if unique_id in self.pending_requests:
                self.pending_requests.pop(unique_id)
            raise  # Re-raise the timeout error so the caller can handle it.

    async def start(self):
        """
        Starts the two main tasks for this connection:
        1. Listening for incoming messages.
        2. Executing the server-initiated logic (test sequence, periodic checks).
        """
        logger.info(f"New connection from Charge Point: {self.charge_point_id}")
        if not self.charge_point_id:
            logger.warning("Connection closed: Charge Point ID is missing in the path.")
            await self.websocket.close()
            return

        # Store the handler instance so the web UI can trigger tests.
        # This creates the entry if it doesn't exist and adds the handler.
        if self.charge_point_id not in CHARGE_POINTS:
            CHARGE_POINTS[self.charge_point_id] = {}
        CHARGE_POINTS[self.charge_point_id]['ocpp_handler'] = self

        self.logic_task = asyncio.create_task(self.run_logic_and_periodic_tasks())
        logger.info(f"Main logic task for {self.charge_point_id} created and running.")

        try:
            # Main message-receiving loop.
            async for message in self.websocket:
                await self.process_message(message)
        finally:
            self.stop()

    def stop(self):
        """Cancels the background tasks and cleans up state."""
        logger.info(f"Connection with {self.charge_point_id} closing. Cancelling logic task.")
        if self.logic_task and not self.logic_task.done():
            self.logic_task.cancel()
        # Remove the charge point from the global state on disconnect.
        if self.charge_point_id in CHARGE_POINTS:
            del CHARGE_POINTS[self.charge_point_id]
        # Since pending_requests is now an instance variable, it will be garbage
        # collected along with the handler instance. No explicit cleanup needed.

    async def run_logic_and_periodic_tasks(self):
        """
        Runs the full initialization sequence followed by periodic checks.
        This is the dedicated background task.
        """
        try:
            # The automatic test sequence is now disabled. The server will wait for
            # commands to be triggered manually from the Web UI.
            logger.info(f"Connection handler for {self.charge_point_id} is ready and waiting for commands from the Web UI.")
            # Keep this task alive to wait for cancellation on disconnect.
            await asyncio.Future()
        except asyncio.CancelledError:
            logger.info(f"Logic task for {self.charge_point_id} was successfully cancelled.")
        except Exception as e:
            logger.error(f"An error occurred in the logic for {self.charge_point_id}: {e}", exc_info=True)
            self.stop()

    async def process_message(self, message: str):
        """Parses and handles a single incoming OCPP message."""
        try:
            msg = json.loads(message)
            message_type_id = msg[0]
            unique_id = msg[1]
        except (json.JSONDecodeError, IndexError) as e:
            logger.error(f"Failed to parse OCPP message: {e}")
            return

        if message_type_id == 2:  # CALL (Request from CP)
            await self.handle_call(unique_id, msg[2], msg[3])
        elif message_type_id == 3:  # CALLRESULT (Response from CP)
            await self.handle_call_result(unique_id, msg[2])
        elif message_type_id == 4:  # CALLERROR (Error from CP)
            await self.handle_call_error(unique_id, msg[2], msg[3], msg[4] if len(msg) > 4 else {})

    async def handle_call(self, unique_id: str, action: str, payload_dict: Dict):
        """Handles a request initiated by the charge point."""
        logger.debug(f"Received CALL for action '{action}' from {self.charge_point_id}")
        
        if action in MESSAGE_HANDLERS:
            handler_info = MESSAGE_HANDLERS[action]
            handler = handler_info["handler"]
            payload_class = handler_info["payload_class"]
            
            try:
                payload = payload_class(**payload_dict)
            except TypeError as e:
                logger.error(f"Payload validation failed for '{action}': {e}")
                response_message = create_ocpp_message(4, unique_id, {"code": "ProtocolError", "description": str(e)})
                await self.websocket.send(response_message)
                return
            
            response_payload = await handler(self.charge_point_id, payload)
            
            if response_payload is not None:
                response_message = create_ocpp_message(3, unique_id, response_payload)
                await self.websocket.send(response_message)
                logger.info(f"Sent response for action '{action}' to {self.charge_point_id}")
        else:
            logger.warning(f"No handler found for action '{action}'")
            response_message = create_ocpp_message(4, unique_id, {"code": "NotSupported", "description": "Action not supported"})
            await self.websocket.send(response_message)