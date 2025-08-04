"""
This module contains the core WebSocket server implementation for the OCPP server.
It uses the `websockets` library to listen for connections, handle incoming
OCPP messages, and dispatch them to the appropriate handler functions.
"""
import asyncio
import json
import logging
from typing import Any, Callable, Dict, List
from websockets.server import serve, WebSocketServerProtocol
from websockets.exceptions import ConnectionClosedOK

from .handlers import (
    handle_boot_notification,
    handle_authorize,
    handle_data_transfer,
    handle_status_notification,
    handle_heartbeat,
    handle_start_transaction,
    handle_stop_transaction,
    # Import new handlers for responses
    handle_get_configuration_response,
    handle_change_configuration_response,
    handle_trigger_message_response,
    handle_meter_values,
    handle_get_composite_schedule_response
)
from .messages import (
    BootNotificationRequest,
    AuthorizeRequest,
    DataTransferRequest,
    StatusNotificationRequest,
    HeartbeatRequest,
    StartTransactionRequest,
    StopTransactionRequest,
    # Import new payloads for requests and responses
    GetConfigurationResponse,
    ChangeConfigurationResponse,
    TriggerMessageResponse,
    MeterValuesRequest,
    GetCompositeScheduleResponse
)

# Configure logging for this module
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# A simple in-memory mapping of message actions to their handlers and payload classes
# This allows for dynamic dispatch based on the incoming message's "Action" field.
MESSAGE_HANDLERS: Dict[str, Dict[str, Any]] = {
    # Handlers for requests from Charge Point
    "BootNotification": {
        "handler": handle_boot_notification,
        "payload_class": BootNotificationRequest,
    },
    "Authorize": {
        "handler": handle_authorize,
        "payload_class": AuthorizeRequest,
    },
    "DataTransfer": {
        "handler": handle_data_transfer,
        "payload_class": DataTransferRequest,
    },
    "StatusNotification": {
        "handler": handle_status_notification,
        "payload_class": StatusNotificationRequest,
    },
    "Heartbeat": {
        "handler": handle_heartbeat,
        "payload_class": HeartbeatRequest,
    },
    "StartTransaction": {
        "handler": handle_start_transaction,
        "payload_class": StartTransactionRequest,
    },
    "StopTransaction": {
        "handler": handle_stop_transaction,
        "payload_class": StopTransactionRequest,
    },
    "MeterValues": {
        "handler": handle_meter_values,
        "payload_class": MeterValuesRequest,
    },
    # Handlers for replies to server-initiated messages
    "GetConfiguration": {
        "handler": handle_get_configuration_response,
        "payload_class": GetConfigurationResponse,
        "is_response": True,
    },
    "ChangeConfiguration": {
        "handler": handle_change_configuration_response,
        "payload_class": ChangeConfigurationResponse,
        "is_response": True,
    },
    "TriggerMessage": {
        "handler": handle_trigger_message_response,
        "payload_class": TriggerMessageResponse,
        "is_response": True,
    },
    "GetCompositeSchedule": {
        "handler": handle_get_composite_schedule_response,
        "payload_class": GetCompositeScheduleResponse,
        "is_response": True,
    },
}

def create_ocpp_message(
    message_type_id: int, unique_id: str, payload: Any, action: str = None
) -> str:
    """
    Creates a JSON-formatted OCPP message array.
    """
    # Use the payload's dictionary representation if available, otherwise use the payload directly
    payload_to_send = payload.__dict__ if hasattr(payload, '__dict__') else payload
    if action:
        return json.dumps([message_type_id, unique_id, action, payload_to_send])
    return json.dumps([message_type_id, unique_id, payload_to_send])


async def serve_ocpp(websocket: WebSocketServerProtocol, path: str):
    """
    The main WebSocket handler function for the OCPP server.
    It handles incoming connections and processes OCPP messages.
    """
    charge_point_id = path.strip("/")
    logger.info(f"New connection from Charge Point: {charge_point_id}")
    
    if not charge_point_id:
        logger.warning("Connection closed: Charge Point ID is missing in the path.")
        await websocket.close()
        return

    try:
        async for message in websocket:
            # An OCPP message is a JSON-encoded array.
            # Example: [2, "unique-id", "BootNotification", { "chargePointVendor": "...", ... }]
            try:
                message_array: List[Any] = json.loads(message)
                message_type_id = message_array[0]
                unique_id = message_array[1]
                # A CALL (2) has an Action and a Payload.
                # A CALLRESULT (3) has only a Payload.
                action = message_array[2] if message_type_id == 2 else None
                payload_dict = message_array[3] if message_type_id == 2 else message_array[2]
                
                logger.debug(f"Received message from {charge_point_id} with action '{action}'")

            except (json.JSONDecodeError, IndexError) as e:
                logger.error(f"Failed to parse OCPP message: {e}")
                # A real server would send a CALLERROR here.
                continue

            # Check if we have a handler for this action
            if action in MESSAGE_HANDLERS:
                handler_info = MESSAGE_HANDLERS[action]
                handler = handler_info["handler"]
                payload_class = handler_info["payload_class"]
                
                # Instantiate the payload class with the received data
                # This may fail if the payload doesn't match the expected class.
                try:
                    payload = payload_class(**payload_dict)
                except TypeError as e:
                    logger.error(f"Payload validation failed for action '{action}': {e}")
                    # Send a CALLERROR for a malformed payload
                    response_message = create_ocpp_message(4, unique_id, {"code": "ProtocolError", "description": str(e)})
                    await websocket.send(response_message)
                    continue
                
                # Call the appropriate handler
                response_payload = await handler(charge_point_id, payload)
                
                # Only send a response if the handler returned a payload.
                # This is for handlers of messages initiated by the Charge Point.
                if response_payload is not None:
                    # OCPP responses are of type CALLRESULT (MessageTypeId = 3)
                    response_message = create_ocpp_message(3, unique_id, response_payload)
                    await websocket.send(response_message)
                    logger.info(f"Sent response for action '{action}' to {charge_point_id}")
                
            else:
                logger.warning(f"No handler found for action '{action}'")
                # A real server would send a CALLERROR for unsupported actions.
                response_message = create_ocpp_message(4, unique_id, {"code": "NotSupported", "description": "Action not supported"})
                await websocket.send(response_message)
                
    except ConnectionClosedOK:
        logger.info(f"Connection from Charge Point {charge_point_id} closed gracefully.")
    except Exception as e:
        logger.error(f"An error occurred with connection {charge_point_id}: {e}")
    finally:
        logger.info(f"Charge Point {charge_point_id} disconnected.")

async def main():
    """
    The main entry point for the server application.
    """
    host = "0.0.0.0"
    port = 8887
    
    logger.info(f"Starting OCPP server on ws://{host}:{port}")
    async with serve(serve_ocpp, host, port):
        await asyncio.Future()  # run forever
