"""
This module contains the core WebSocket server implementation for the OCPP server.
It uses the `websockets` library to listen for connections, handle incoming
OCPP messages, and dispatch them to the appropriate handler functions.
"""
import asyncio, uuid, random
import json
import logging
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Dict, List
from websockets.server import serve, WebSocketServerProtocol
from websockets.exceptions import ConnectionClosedOK

from .handlers import (
    handle_boot_notification,
    handle_authorize,
    handle_data_transfer,
    handle_status_notification,
    handle_firmware_status_notification,
    handle_diagnostics_status_notification,
    handle_heartbeat,
    handle_start_transaction,
    handle_stop_transaction,
    # Import new handlers for responses
    handle_change_availability_response,
    handle_get_configuration_response,
    handle_change_configuration_response,
    handle_trigger_message_response,
    handle_meter_values,
    handle_get_composite_schedule_response,
    # === NEW: Import handler for SetChargingProfile response ===
    handle_set_charging_profile_response,
    # Import the in-memory storage dictionaries
    CHARGE_POINTS
)
from .messages import (
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
    # Import new payloads for requests and responses
    ChangeAvailabilityResponse,
    GetConfigurationResponse,
    ChangeConfigurationResponse,
    TriggerMessageResponse,
    GetCompositeScheduleResponse,
    # Import new payloads for server-initiated requests
    ChangeAvailabilityRequest,
    GetConfigurationRequest,
    TriggerMessageRequest,
    ChangeConfigurationRequest,
    GetCompositeScheduleRequest,
    # === NEW: Import SetChargingProfile payloads ===
    SetChargingProfileRequest,
    SetChargingProfileResponse,
    ChargingProfile,
    ChargingSchedule,
    ChargingSchedulePeriod,
    ChargingProfilePurposeType,
    ChargingProfileKindType,
    ChargingRateUnitType,
    ChargingProfileStatusType
)

# Configure logging for this module
# Changing the level to DEBUG or TRACE will show all sent and received messages.
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# A dictionary to track pending server-initiated requests and their corresponding events.
# This allows us to wait for a specific response before proceeding.
# Format: { "unique_id": {"action": str, "event": asyncio.Event} }
PENDING_REQUESTS: Dict[str, Dict[str, Any]] = {}

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
    "FirmwareStatusNotification": {
        "handler": handle_firmware_status_notification,
        "payload_class": FirmwareStatusNotificationRequest,
    },
    "DiagnosticsStatusNotification": {
        "handler": handle_diagnostics_status_notification,
        "payload_class": DiagnosticsStatusNotificationRequest,
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
    "ChangeAvailability": {
        "handler": handle_change_availability_response,
        "payload_class": ChangeAvailabilityResponse,
    },
    "GetConfiguration": {
        "handler": handle_get_configuration_response,
        "payload_class": GetConfigurationResponse,
    },
    "ChangeConfiguration": {
        "handler": handle_change_configuration_response,
        "payload_class": ChangeConfigurationResponse,
    },
    "TriggerMessage": {
        "handler": handle_trigger_message_response,
        "payload_class": TriggerMessageResponse,
    },
    "GetCompositeSchedule": {
        "handler": handle_get_composite_schedule_response,
        "payload_class": GetCompositeScheduleResponse,
    },
    # === NEW: Handler for SetChargingProfile response ===
    "SetChargingProfile": {
        "handler": handle_set_charging_profile_response,
        "payload_class": SetChargingProfileResponse,
    }
}

def create_ocpp_message(
    message_type_id: int, unique_id: str, payload: Any, action: str = None
) -> str:
    """
    Creates a JSON-formatted OCPP message array.
    """
    # Use dataclasses.asdict for proper serialization of dataclass objects.
    # Fall back to the object itself for non-dataclass payloads (like error dicts).
    # The dict_factory is crucial for creating compliant OCPP messages, as it
    # omits optional fields that have a value of None. Some charge points
    # are overly strict and will reject messages containing "key": null.
    dict_factory = lambda data: {k: v for (k, v) in data if v is not None}
    payload_to_send = asdict(payload, dict_factory=dict_factory) if is_dataclass(payload) else payload
    
    if action:
        message = [message_type_id, unique_id, action, payload_to_send]
    else:
        message = [message_type_id, unique_id, payload_to_send]
        
    logger.debug(f"Sending message: {json.dumps(message)}")
    return json.dumps(message)


# =================================================================================
# Helper functions for server-initiated commands
# =================================================================================

async def send_change_availability(websocket: WebSocketServerProtocol, connector_id: int, type: str):
    """Sends a ChangeAvailability request and waits for a response."""
    unique_id = str(uuid.uuid4())
    event = asyncio.Event()
    PENDING_REQUESTS[unique_id] = {"action": "ChangeAvailability", "event": event}
    logger.debug(f"PENDING_REQUESTS: Added {unique_id} for ChangeAvailability")
    request = ChangeAvailabilityRequest(connectorId=connector_id, type=type)
    message = create_ocpp_message(2, unique_id, request, "ChangeAvailability")
    await websocket.send(message)
    logger.info(f"Sent ChangeAvailability (id={unique_id}) for connector {connector_id} to '{type}'. Waiting for response...")
    await event.wait()
    logger.info(f"Response received for ChangeAvailability (id={unique_id}). Proceeding.")

async def send_get_configuration(websocket: WebSocketServerProtocol):
    """Sends a GetConfiguration request and waits for a response."""
    unique_id = str(uuid.uuid4())
    event = asyncio.Event()
    PENDING_REQUESTS[unique_id] = {"action": "GetConfiguration", "event": event}
    logger.debug(f"PENDING_REQUESTS: Added {unique_id} for GetConfiguration")
    request = GetConfigurationRequest()
    message = create_ocpp_message(2, unique_id, request, "GetConfiguration")
    await websocket.send(message)
    logger.info(f"Sent GetConfiguration request (id={unique_id}). Waiting for response...")
    await event.wait()
    logger.info(f"Response received for GetConfiguration (id={unique_id}). Proceeding.")

async def send_change_configuration(websocket: WebSocketServerProtocol, key: str, value: str):
    """Sends a ChangeConfiguration request and waits for a response."""
    unique_id = str(uuid.uuid4())
    event = asyncio.Event()
    PENDING_REQUESTS[unique_id] = {"action": "ChangeConfiguration", "event": event}
    logger.debug(f"PENDING_REQUESTS: Added {unique_id} for ChangeConfiguration")
    request = ChangeConfigurationRequest(key=key, value=value)
    message = create_ocpp_message(2, unique_id, request, "ChangeConfiguration")
    await websocket.send(message)
    logger.info(f"Sent ChangeConfiguration request (id={unique_id}) for key '{key}' with value '{value}'. Waiting for response...")
    await event.wait()
    logger.info(f"Response received for ChangeConfiguration (id={unique_id}). Proceeding.")

async def send_trigger_message(websocket: WebSocketServerProtocol, requested_message: str, connector_id: int = None):
    """Sends a TriggerMessage request and waits for a response."""
    # Your analysis is correct. Messages like StatusNotification and MeterValues
    # require a valid integer connectorId. This validation prevents sending a malformed
    # request that would result in a TypeConstraintViolation from the charge point.
    if requested_message in ["StatusNotification", "MeterValues"] and not isinstance(connector_id, int):
        logger.error(
            f"Cannot send TriggerMessage for '{requested_message}': a valid integer connectorId is required."
        )
        # Returning here prevents the server from sending a message that is guaranteed to fail.
        return

    unique_id = str(uuid.uuid4())
    event = asyncio.Event()
    PENDING_REQUESTS[unique_id] = {"action": "TriggerMessage", "event": event}
    logger.debug(f"PENDING_REQUESTS: Added {unique_id} for TriggerMessage")
    request = TriggerMessageRequest(requestedMessage=requested_message, connectorId=connector_id)
    message = create_ocpp_message(2, unique_id, request, "TriggerMessage")
    await websocket.send(message)
    logger.info(f"Sent TriggerMessage (id={unique_id}) for '{requested_message}'" + (f" for connector {connector_id}" if connector_id is not None else "") + ". Waiting for response...")
    await event.wait()
    logger.info(f"Response received for TriggerMessage (id={unique_id}). Proceeding.")

async def send_get_composite_schedule(
    websocket: WebSocketServerProtocol, connector_id: int, duration: int, charging_rate_unit: str = None
):
    """Sends a GetCompositeSchedule request and waits for a response."""
    unique_id = str(uuid.uuid4())
    event = asyncio.Event()
    PENDING_REQUESTS[unique_id] = {"action": "GetCompositeSchedule", "event": event}
    logger.debug(f"PENDING_REQUESTS: Added {unique_id} for GetCompositeSchedule")
    request = GetCompositeScheduleRequest(
        connectorId=connector_id, duration=duration, chargingRateUnit=charging_rate_unit
    )
    message = create_ocpp_message(2, unique_id, request, "GetCompositeSchedule")
    await websocket.send(message)
    log_message = f"Sent GetCompositeSchedule (id={unique_id}) for connector {connector_id} with duration {duration}"
    if charging_rate_unit:
        log_message += f" and chargingRateUnit '{charging_rate_unit}'"
    log_message += ". Waiting for response..."
    logger.info(log_message)
    await event.wait()
    logger.info(f"Response received for GetCompositeSchedule (id={unique_id}). Proceeding.")

# === NEW: Helper function for SetChargingProfile ===
async def send_set_charging_profile(
    websocket: WebSocketServerProtocol, connector_id: int, limit_watts: int, duration_seconds: int, profile_purpose: str
):
    """Sends a SetChargingProfile request and waits for a response."""
    unique_id = str(uuid.uuid4())
    event = asyncio.Event()
    PENDING_REQUESTS[unique_id] = {"action": "SetChargingProfile", "event": event}
    logger.debug(f"PENDING_REQUESTS: Added {unique_id} for SetChargingProfile")
    
    # The chargingProfileId should be unique for each profile set.
    # A simple approach is to use a random number.
    profile_id = random.randint(1, 100)

    request = SetChargingProfileRequest(
        connectorId=connector_id,
        csChargingProfiles=ChargingProfile(
            chargingProfileId=profile_id,
            stackLevel=0,
            chargingProfilePurpose=profile_purpose,
            chargingProfileKind=ChargingProfileKindType.Absolute,
            chargingSchedule=ChargingSchedule(
                chargingRateUnit=ChargingRateUnitType.W,
                duration=duration_seconds,
                chargingSchedulePeriod=[
                    ChargingSchedulePeriod(
                        startPeriod=0,
                        limit=limit_watts
                    )
                ]
            )
        )
    )
    
    message = create_ocpp_message(2, unique_id, request, "SetChargingProfile")
    await websocket.send(message)
    logger.info(f"Sent SetChargingProfile (id={unique_id}, purpose={profile_purpose}) for connector {connector_id} with a limit of {limit_watts}W for {duration_seconds}s. Waiting for response...")
    await event.wait()
    logger.info(f"Response received for SetChargingProfile (id={unique_id}). Proceeding.")


async def configure_meter_values(websocket: WebSocketServerProtocol):
    """
    Sends a sequence of ChangeConfiguration requests to set the MeterValuesSampledData.
    This mimics the behavior observed in the log file.
    """
    values = [
        "Power.Active.Import",
        "Energy.Active.Import.Register",
        "Current.Import",
        "Voltage",
        "Current.Offered",
        "Power.Offered",
        "SoC"
    ]
    
    # Set individual values first (as seen in logs)
    for value in values:
        await send_change_configuration(websocket, "MeterValuesSampledData", value)
        await asyncio.sleep(1)  # Small delay between requests
    
    # Set combined value
    combined = ",".join(values)
    await send_change_configuration(websocket, "MeterValuesSampledData", combined)

async def periodic_status_checks(websocket: WebSocketServerProtocol, charge_point_id: str):
    """
    A coroutine that periodically requests status and meter values.
    This runs for as long as the WebSocket connection is active.
    """
    try:
        # This loop now runs indefinitely until the task is cancelled (e.g., on disconnect).
        cycle_count = 0
        while True:
            cycle_count += 1
            logger.info(f"Initiating periodic status and meter value checks for {charge_point_id}... (Cycle {cycle_count})")
            await send_trigger_message(websocket, "StatusNotification", connector_id=1)
            await send_trigger_message(websocket, "MeterValues", connector_id=1)
            await asyncio.sleep(60)  # Check every minute
    except asyncio.CancelledError:
        # This exception is raised when the task is cancelled.
        logger.info(f"Periodic check for {charge_point_id} was cancelled.")
    except ConnectionClosedOK:
        logger.info(f"Periodic check for {charge_point_id} stopped due to connection closure.")
    except Exception as e:
        logger.error(f"An error occurred during periodic checks for {charge_point_id}: {e}")


async def initialize_wallbox(websocket: WebSocketServerProtocol, charge_point_id: str):
    """
    The main initialization sequence for a newly connected Charge Point.
    This function orchestrates the requests based on the provided log file analysis.
    """
    logger.info(f"Starting initialization sequence for {charge_point_id}...")

    # Step 1: Initial Connection and Registration.
    # Set the charge point to be operative. The charge point should respond with
    # a StatusNotification confirming it is "Available".
    print("\n--------------------- 1. Initial Connection and Registration --------------------")
    await send_change_availability(websocket, connector_id=0, type="Operative")

    # Step 2: Configuration Exchange.
    print("\n--------------------- 2. Configuration Exchange --------------------")
    # Retrieve the wallbox's current settings.
    await send_get_configuration(websocket)
    # Trigger a boot notification to ensure the charge point is fully registered.
    await send_trigger_message(websocket, requested_message="BootNotification")
    # Set various meter-related configurations.
    await configure_meter_values(websocket)
    await send_change_configuration(websocket, "MeterValueSampleInterval", "10")
    # Set a ping interval, which the wallbox might not support (as per logs).
    await send_change_configuration(websocket, "WebSocketPingInterval", "60")

    # Step 3: Status and Meter Value Acquisition.
    print("\n--------------------- 3. Status and Meter Value Acquisition --------------------")
    await send_trigger_message(websocket, "StatusNotification", connector_id=1)
    await send_trigger_message(websocket, "MeterValues", connector_id=1)

    # Step 4: Smart Charging Capability Test.
    print("\n--------------------- 4. Smart Charging Capability Test --------------------")
    await send_get_composite_schedule(websocket, connector_id=1, duration=60, charging_rate_unit="W")

    # === NEW: Step 5. Set Charging Power ===
    print("\n---------------5. Set Charging Power-------------------")
    await send_set_charging_profile(
        websocket, connector_id=1, limit_watts=5000, duration_seconds=60, profile_purpose=ChargingProfilePurposeType.TxProfile
    )

    # === NEW: Step 6. Set Default Profile ===
    print("\n----------------------6:Set default profile-----------------------")
    # This profile sets a default for all transactions on connector 1.
    # We use a different limit and a longer duration to distinguish it.
    await send_set_charging_profile(
        websocket, connector_id=1, limit_watts=7000, duration_seconds=3600, profile_purpose=ChargingProfilePurposeType.TxDefaultProfile
    )

    logger.info(f"Initialization test sequence for {charge_point_id} complete.")
    logger.info("========================END OF TEST SEQUENCE==============================")


async def serve_ocpp(websocket: WebSocketServerProtocol):
    """
    The main WebSocket handler function for the OCPP server.
    It handles incoming connections and processes OCPP messages for a single charge point.
    """
    path = websocket.path
    charge_point_id = path.strip("/")
    logger.info(f"New connection from Charge Point: {charge_point_id}")
    if not charge_point_id:
        logger.warning("Connection closed: Charge Point ID is missing in the path.")
        await websocket.close()
        return

    logic_task = None

    async def run_logic_sequence():
        """A wrapper function to run initialization and then periodic checks."""
        logger.info(f"Starting logic sequence task for {charge_point_id}...")
        try:
            if charge_point_id not in CHARGE_POINTS:
                await initialize_wallbox(websocket, charge_point_id)
            else:
                logger.info(f"Charge Point {charge_point_id} is already initialized. Skipping setup.")
            
            logger.info(f"Logic sequence for {charge_point_id} completed. Server is now in passive listening mode.")
        except ConnectionClosedOK:
            logger.info(f"Logic sequence for {charge_point_id} stopped due to connection closure.")
        except Exception as e:
            logger.error(f"An error occurred in the logic sequence for {charge_point_id}: {e}", exc_info=True)


    logic_task = asyncio.create_task(run_logic_sequence())
    logger.info(f"Logic task for {charge_point_id} created and running in background.")

    try:
        async for message in websocket:
            logger.debug(f"RAW << {charge_point_id}: {message}")
            try:
                msg = json.loads(message)
                message_type_id = msg[0]
                unique_id = msg[1]
            except (json.JSONDecodeError, IndexError) as e:
                logger.error(f"Failed to parse OCPP message: {e}")
                continue

            # Handle CALL messages (initiated by Charge Point)
            if message_type_id == 2:
                action = msg[2]
                payload_dict = msg[3]
                logger.debug(f"Received CALL for action '{action}' from {charge_point_id}")

                if action in MESSAGE_HANDLERS:
                    handler_info = MESSAGE_HANDLERS[action]
                    handler = handler_info["handler"]
                    payload_class = handler_info["payload_class"]
                    
                    try:
                        payload = payload_class(**payload_dict)
                    except TypeError as e:
                        logger.error(f"Payload validation failed for action '{action}': {e}")
                        response_message = create_ocpp_message(4, unique_id, {"code": "ProtocolError", "description": str(e)})
                        await websocket.send(response_message)
                        continue
                    
                    response_payload = await handler(charge_point_id, payload)
                    
                    if response_payload is not None:
                        response_message = create_ocpp_message(3, unique_id, response_payload)
                        await websocket.send(response_message)
                        logger.info(f"Sent response for action '{action}' to {charge_point_id}")
                else:
                    logger.warning(f"No handler found for action '{action}'")
                    response_message = create_ocpp_message(4, unique_id, {"code": "NotSupported", "description": "Action not supported"})
                    await websocket.send(response_message)

            # Handle CALLRESULT messages (responses to server-initiated commands)
            elif message_type_id == 3:
                payload_dict = msg[2]
                logger.debug(f"Received CALLRESULT with unique_id: {unique_id}")
                if unique_id in PENDING_REQUESTS:
                    logger.debug(f"Found matching unique_id {unique_id} in PENDING_REQUESTS.")
                    pending_request = PENDING_REQUESTS.pop(unique_id)
                    action = pending_request["action"]
                    event = pending_request["event"]

                    logger.info(f"Received response for server-initiated action '{action}'")

                    if action in MESSAGE_HANDLERS:
                        handler_info = MESSAGE_HANDLERS[action]
                        handler = handler_info["handler"]
                        payload_class = handler_info["payload_class"]
                        try:
                            payload = payload_class(**payload_dict)
                            await handler(charge_point_id, payload)
                        except TypeError as e:
                            logger.error(f"Payload validation failed for response action '{action}': {e}")
                    else:
                        logger.warning(f"No handler found for response action '{action}'")

                    # Unblock the waiting coroutine regardless of the outcome
                    logger.debug(f"Setting event for unique_id {unique_id} to unblock waiting task.")
                    event.set()
                else:
                    logger.warning(f"Received unsolicited CALLRESULT with unique_id: {unique_id}. PENDING_REQUESTS: {list(PENDING_REQUESTS.keys())}")

            # Handle CALLERROR messages (errors in response to server-initiated commands)
            elif message_type_id == 4:
                error_code = msg[2]
                error_description = msg[3]
                error_details = msg[4] if len(msg) > 4 else {}
                logger.error(f"Received CALLERROR from {charge_point_id}: {error_code} - {error_description} {error_details}")

                if unique_id in PENDING_REQUESTS:
                    logger.debug(f"Found matching unique_id {unique_id} in PENDING_REQUESTS for CALLERROR.")
                    pending_request = PENDING_REQUESTS.pop(unique_id)
                    action = pending_request["action"]
                    event = pending_request["event"]
                    logger.warning(f"Server-initiated action '{action}' failed.")
                    # Unblock the waiting coroutine, even on error
                    logger.debug(f"Setting event for unique_id {unique_id} to unblock waiting task after error.")
                    event.set()
                else:
                    logger.warning(f"Received unsolicited CALLERROR with unique_id: {unique_id}. PENDING_REQUESTS: {list(PENDING_REQUESTS.keys())}")
                
    except ConnectionClosedOK:
        logger.info(f"Connection from Charge Point {charge_point_id} closed gracefully.")
    except Exception as e:
        logger.error(f"An error occurred with connection {charge_point_id}: {e}")
    finally:
        logger.info(f"Charge Point {charge_point_id} disconnected.")
        # Clean up the background task when the connection is closed.
        if logic_task:
            logic_task.cancel()