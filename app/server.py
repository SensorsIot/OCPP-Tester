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
    handle_clear_charging_profile_response,
    handle_set_charging_profile_response,
)
from .state import CHARGE_POINTS, TRANSACTIONS
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
    # === NEW: Import ClearChargingProfile payloads ===
    ClearChargingProfileRequest,
    ClearChargingProfileResponse,
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
    # === NEW: Handler for ClearChargingProfile response ===
    "ClearChargingProfile": {
        "handler": handle_clear_charging_profile_response,
        "payload_class": ClearChargingProfileResponse,
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
        
    logger.debug("\n\n------------OCPP Call----------")
    return json.dumps(message)


# =================================================================================
# Helper functions for server-initiated commands
# =================================================================================

async def send_and_wait(websocket: WebSocketServerProtocol, action: str, request_payload: Any, timeout: int = 30):
    """
    A generic function to send a server-initiated request and wait for its response.
    This centralizes the logic for sending, tracking pending requests, and handling timeouts.
    """
    unique_id = str(uuid.uuid4())
    event = asyncio.Event()
    PENDING_REQUESTS[unique_id] = {"action": action, "event": event}
    logger.debug(f"PENDING_REQUESTS: Added {unique_id} for {action}")

    message = create_ocpp_message(2, unique_id, request_payload, action)
    await websocket.send(message)
    logger.info(f"Sent {action} (id={unique_id}). Waiting for response...")

    try:
        # Wait for the event to be set, with a timeout.
        await asyncio.wait_for(event.wait(), timeout=timeout)
        logger.info(f"Response received for {action} (id={unique_id}). Proceeding.")
    except asyncio.TimeoutError:
        logger.error(f"Timeout: No response received for {action} (id={unique_id}) within {timeout} seconds.")
        # Clean up the pending request to prevent memory leaks.
        if unique_id in PENDING_REQUESTS:
            PENDING_REQUESTS.pop(unique_id)

async def send_change_availability(websocket: WebSocketServerProtocol, connector_id: int, type: str):
    """Sends a ChangeAvailability request."""
    request = ChangeAvailabilityRequest(connectorId=connector_id, type=type)
    await send_and_wait(websocket, "ChangeAvailability", request)

async def send_get_configuration(websocket: WebSocketServerProtocol):
    """Sends a GetConfiguration request."""
    request = GetConfigurationRequest()
    await send_and_wait(websocket, "GetConfiguration", request)

async def send_change_configuration(websocket: WebSocketServerProtocol, key: str, value: str):
    """Sends a ChangeConfiguration request."""
    request = ChangeConfigurationRequest(key=key, value=value)
    await send_and_wait(websocket, "ChangeConfiguration", request)

async def send_trigger_message(websocket: WebSocketServerProtocol, requested_message: str, connector_id: int = None):
    """Sends a TriggerMessage request."""
    if requested_message in ["StatusNotification", "MeterValues"] and not isinstance(connector_id, int):
        logger.error(
            f"Cannot send TriggerMessage for '{requested_message}': a valid integer connectorId is required."
        )
        return

    request = TriggerMessageRequest(requestedMessage=requested_message, connectorId=connector_id)
    await send_and_wait(websocket, "TriggerMessage", request)

async def send_get_composite_schedule(
    websocket: WebSocketServerProtocol, connector_id: int, duration: int, charging_rate_unit: str = None
):
    """Sends a GetCompositeSchedule request."""
    request = GetCompositeScheduleRequest(
        connectorId=connector_id, duration=duration, chargingRateUnit=charging_rate_unit
    )
    await send_and_wait(websocket, "GetCompositeSchedule", request)

# === NEW: Helper function for SetChargingProfile ===
async def send_set_charging_profile(
    websocket: WebSocketServerProtocol, connector_id: int, limit_watts: int, duration_seconds: int, profile_purpose: str
):
    """Builds and sends a SetChargingProfile request."""
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
    await send_and_wait(websocket, "SetChargingProfile", request)

async def send_clear_charging_profile(
    websocket: WebSocketServerProtocol, connector_id: int = None, charging_profile_purpose: str = None
):
    """Builds and sends a ClearChargingProfile request."""
    request = ClearChargingProfileRequest(
        connectorId=connector_id,
        chargingProfilePurpose=charging_profile_purpose
    )
    await send_and_wait(websocket, "ClearChargingProfile", request)

async def test_user_initiated_transaction(charge_point_id: str):
    """
    A test sequence to guide the user through a manual, user-initiated transaction.
    The server will wait for the charge point to send Authorize and StartTransaction requests.
    """
    logger.info("\n\n\n\n\n--- Step 3: User-Initiated Transaction Test ---")
    logger.info("This step tests the server's ability to handle a standard, user-initiated charging session.")
    logger.info("The server will now wait for 30 seconds for a manual authorization.")
    logger.info("ACTION REQUIRED: To proceed with this test, please present a valid ID tag (e.g., 'test_id_1') to the physical charge point.")
    logger.info("The server will automatically handle the Authorize.req, StartTransaction.req, and subsequent StatusNotification (to 'Charging').")

    # Wait for the user to interact with the charge point
    await asyncio.sleep(30)

    # After waiting, check if a transaction was successfully created.
    # This confirms the server correctly handled the sequence of messages from the charge point.
    active_transaction = any(
        t.get("charge_point_id") == charge_point_id and "stop_time" not in t
        for t in TRANSACTIONS.values()
    )

    if active_transaction:
        logger.info("SUCCESS: An active transaction was detected for this charge point.")
        logger.info("The server successfully processed the Authorize.req and StartTransaction.req messages.")
    else:
        logger.warning("NOTICE: No new transaction was detected for this charge point in the last 30 seconds.")
        logger.warning("The test will continue, but the user-initiated transaction flow was not verified.")

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

    # Set the charge point to be operative. The charge point should respond with
    # a StatusNotification confirming it is "Available".
    logger.info("\n\n\n\n\n--- Step 1: Initial Connection and Registration ---")
    await send_change_availability(websocket, connector_id=0, type="Operative")

    # Configuration Exchange.
    logger.info("\n\n\n\n\n--- Step 2: Configuration Exchange ---")
    # Retrieve the wallbox's current settings.
    await send_get_configuration(websocket)
    # Trigger a boot notification to ensure the charge point is fully registered.
    await send_trigger_message(websocket, requested_message="BootNotification")
    # Set various meter-related configurations.
    await configure_meter_values(websocket)
    await send_change_configuration(websocket, "MeterValueSampleInterval", "10")
    # Set a ping interval, which the wallbox might not support (as per logs).
    await send_change_configuration(websocket, "WebSocketPingInterval", "60")
    
    # This test simulates a user starting a charge session from the wallbox itself.
    # This test simulates a user starting a charge session from the wallbox itself.
    await test_user_initiated_transaction(charge_point_id)

    # Status and Meter Value Acquisition.
    logger.info("\n\n\n\n\n--- Step 4: Status and Meter Value Acquisition ---")
    await send_trigger_message(websocket, "StatusNotification", connector_id=1)
    await send_trigger_message(websocket, "MeterValues", connector_id=1)

    # Smart Charging Capability Test.
    logger.info("\n\n\n\n\n--- Step 5: Smart Charging Capability Test ---")
    await send_get_composite_schedule(websocket, connector_id=1, duration=60, charging_rate_unit="W")

    # Set Charging Power for an active transaction.
    logger.info("\n\n\n\n\n--- Step 6: Set Charging Power (for Active Transaction) ---")
    # A TxProfile can only be set during an active transaction.
    # First, check if there is an active transaction for this charge point.
    active_transaction = any(
        t.get("charge_point_id") == charge_point_id and "stop_time" not in t
        for t in TRANSACTIONS.values()
    )
    if active_transaction:
        logger.info(f"Active transaction found for {charge_point_id}. Proceeding with SetChargingProfile(TxProfile).")
        await send_set_charging_profile(
            websocket, connector_id=1, limit_watts=5000, duration_seconds=60, profile_purpose=ChargingProfilePurposeType.TxProfile
        )
    else:
        logger.warning(f"No active transaction for {charge_point_id}. Skipping SetChargingProfile with TxProfile as it would be rejected.")

    # Set a default charging profile for the connector.
    logger.info("\n\n\n\n\n--- Step 7: Set Default Charging Profile ---")
    # This profile sets a default for all transactions on connector 1.
    # We use a different limit and a longer duration to distinguish it.
    await send_set_charging_profile(
        websocket, connector_id=1, limit_watts=7000, duration_seconds=3600, profile_purpose=ChargingProfilePurposeType.TxDefaultProfile
    )

    # Clear the default charging profile.
    logger.info("\n\n\n\n\n--- Step 8: Clear Default Charging Profile ---")
    # This removes the default profile that was set in the previous step.
    await send_clear_charging_profile(
        websocket, connector_id=1, charging_profile_purpose=ChargingProfilePurposeType.TxDefaultProfile
    )

    logger.info("")
    logger.info("")
    logger.info(f"Initialization test sequence for {charge_point_id} complete.")
    logger.info("========================END OF TEST SEQUENCE==============================")
    # Add 10 empty lines for better log separation before periodic checks begin.
    for _ in range(10):
        logger.info("")



async def serve_ocpp(websocket: WebSocketServerProtocol):
    """
    The main WebSocket handler function for the OCPP server.
    It handles an incoming connection and processes OCPP messages for a single charge point.

    This function uses a two-task design pattern which is essential for this
    kind of bidirectional communication:

    1. The Main Task (this function): Runs an `async for` loop to continuously
       listen for and process all incoming messages from the charge point.

    2. The Background "Logic" Task (`logic_task`): Is created to run all
       server-initiated logic, such as the initialization sequence and
       periodic status checks.

    This separation is crucial because the server-initiated logic needs to send a
    request and then wait (`await`) for a specific response. The main task is
    responsible for receiving that response and notifying the background task
    (via an asyncio.Event), thus avoiding a deadlock.
    """
    path = websocket.path
    charge_point_id = path.strip("/")
    logger.info(f"New connection from Charge Point: {charge_point_id}")
    if not charge_point_id:
        logger.warning("Connection closed: Charge Point ID is missing in the path.")
        await websocket.close()
        return

    async def run_logic_and_periodic_tasks():
        """
        Runs the main logic for a charge point connection. It first performs
        the full initialization sequence and, upon completion, runs periodic
        status checks for the lifetime of the connection.
        """
        try:
            # Step 1: Run the full initialization sequence and wait for it to complete.
            # This ensures the charge point is in a known state before periodic tasks begin.
            logger.info(f"Starting initialization sequence for {charge_point_id}...")
            await initialize_wallbox(websocket, charge_point_id)

            # Step 2: After successful initialization, start the long-running periodic checks.
            # This task will run until the connection is closed or an error occurs.
            logger.info(f"Initialization complete. Starting periodic status checks for {charge_point_id}...")
            await periodic_status_checks(websocket, charge_point_id)

        except ConnectionClosedOK:
            # This is an expected way to exit when the connection is closed by the client.
            logger.info(f"Connection closed for {charge_point_id}. Logic and periodic tasks are stopping.")
        except Exception as e:
            # Catch any other exceptions from the logic sequence.
            logger.error(f"An error occurred in the logic for {charge_point_id}: {e}", exc_info=True)

    # Create a single, managed task for all server-initiated logic. This task
    # runs in the background, allowing the main loop below to handle incoming
    # messages concurrently. The task's lifecycle is tied to the connection.
    logic_task = asyncio.create_task(run_logic_and_periodic_tasks())
    logger.info(f"Main logic task for {charge_point_id} created and running.")

    try:
        # This is the main message-receiving loop. It will run for the entire
        # duration of the WebSocket connection, processing any message sent
        # by the charge point.
        async for message in websocket:
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
                    logger.debug(f"Setting event for unique_id {unique_id} to unblock waiting task.")
                    event.set()
    finally:
        # This block executes when the `async for` loop exits, which typically
        # happens when the WebSocket connection is closed by the client.
        logger.info(f"Connection with {charge_point_id} is closing. Cancelling background logic task.")
        logic_task.cancel()
        try:
            await logic_task
        except asyncio.CancelledError:
            logger.info(f"Background logic task for {charge_point_id} was successfully cancelled.")