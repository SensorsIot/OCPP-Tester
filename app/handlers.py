"""
This module contains the handler functions for each type of OCPP message.
Each handler is responsible for processing the incoming request, updating the
server's state, and returning an appropriate response payload.
"""

import logging
from datetime import datetime, timezone
from .state import CHARGE_POINTS, TRANSACTIONS
from .messages import (
    BootNotificationRequest, BootNotificationResponse,
    AuthorizeRequest, AuthorizeResponse, IdTagInfo,
    DataTransferRequest, DataTransferResponse,
    StatusNotificationRequest, StatusNotificationResponse,
    FirmwareStatusNotificationRequest, FirmwareStatusNotificationResponse,
    DiagnosticsStatusNotificationRequest, DiagnosticsStatusNotificationResponse,
    HeartbeatRequest, HeartbeatResponse,
    StartTransactionRequest, StartTransactionResponse,
    StopTransactionRequest, StopTransactionResponse,
    MeterValuesRequest, MeterValuesResponse,
    # Payloads for responses to server-initiated messages
    ChangeAvailabilityResponse,
    GetConfigurationResponse,
    ChangeConfigurationResponse,
    TriggerMessageResponse,
    GetCompositeScheduleResponse,
    ClearChargingProfileResponse,
    SetChargingProfileResponse,
)

logger = logging.getLogger(__name__)

# A simple, hardcoded list of valid ID tags for authorization.
VALID_ID_TAGS = ["test_id_1", "test_id_2"]

# --- Mapping from OCPP Status to Charge Point (CP) State ---
# As per your request, this maps the status from a StatusNotification
# to a more descriptive internal state for logging. I've assumed that
# "Charging" maps to "CP State C" to follow the logical pattern.
CP_STATE_MAP = {
    "Available": "CP State A",
    "Preparing": "CP State B",
    "Charging": "CP State C",
    "Finishing": "CP State X",
}

async def handle_boot_notification(charge_point_id: str, payload: BootNotificationRequest) -> BootNotificationResponse:
    """Handles a BootNotification request from a charge point."""
    logger.info(f"Received BootNotification from {charge_point_id}: {payload}")
    
    # Store the charge point's info. In a real system, you'd save this to a database.
    CHARGE_POINTS[charge_point_id] = {
        "model": payload.chargePointModel,
        "vendor": payload.chargePointVendor,
        "status": "Available", # Initial status
        "last_heartbeat": datetime.now(timezone.utc).isoformat()
    }
    
    # Return a confirmation response.
    return BootNotificationResponse(
        status="Accepted",
        currentTime=datetime.now(timezone.utc).isoformat(),
        interval=60  # Heartbeat interval in seconds
    )

async def handle_authorize(charge_point_id: str, payload: AuthorizeRequest) -> AuthorizeResponse:
    """Handles an Authorize request."""
    logger.info(f"Received Authorize request from {charge_point_id} for idTag: {payload.idTag}")
    
    status = "Accepted" if payload.idTag in VALID_ID_TAGS else "Invalid"
    
    return AuthorizeResponse(idTagInfo=IdTagInfo(status=status))

async def handle_data_transfer(charge_point_id: str, payload: DataTransferRequest) -> DataTransferResponse:
    """Handles a DataTransfer request."""
    logger.info(f"Received DataTransfer from {charge_point_id}: {payload}")
    return DataTransferResponse(status="Accepted")

async def handle_status_notification(charge_point_id: str, payload: StatusNotificationRequest) -> StatusNotificationResponse:
    """Handles a StatusNotification request."""
    # Get the corresponding CP State from the map, with a fallback for unmapped statuses.
    cp_state_log_message = ""
    if payload.status in CP_STATE_MAP:
        cp_state_log_message = f" (equivalent to {CP_STATE_MAP[payload.status]})"

    logger.info(f"Received StatusNotification from {charge_point_id}: Connector {payload.connectorId} is {payload.status}{cp_state_log_message}")
    if charge_point_id in CHARGE_POINTS:
        CHARGE_POINTS[charge_point_id]["status"] = payload.status
    return StatusNotificationResponse()

async def handle_firmware_status_notification(charge_point_id: str, payload: FirmwareStatusNotificationRequest) -> FirmwareStatusNotificationResponse:
    """Handles a FirmwareStatusNotification request."""
    logger.info(f"Received FirmwareStatusNotification from {charge_point_id}: {payload.status}")
    return FirmwareStatusNotificationResponse()

async def handle_diagnostics_status_notification(charge_point_id: str, payload: DiagnosticsStatusNotificationRequest) -> DiagnosticsStatusNotificationResponse:
    """Handles a DiagnosticsStatusNotification request."""
    logger.info(f"Received DiagnosticsStatusNotification from {charge_point_id}: {payload.status}")
    return DiagnosticsStatusNotificationResponse()

async def handle_heartbeat(charge_point_id: str, payload: HeartbeatRequest) -> HeartbeatResponse:
    """Handles a Heartbeat request."""
    logger.info(f"Received Heartbeat from {charge_point_id}")
    if charge_point_id in CHARGE_POINTS:
        CHARGE_POINTS[charge_point_id]["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
    return HeartbeatResponse(currentTime=datetime.now(timezone.utc).isoformat())

async def handle_start_transaction(charge_point_id: str, payload: StartTransactionRequest) -> StartTransactionResponse:
    """Handles a StartTransaction request."""
    logger.info(f"Received StartTransaction from {charge_point_id} on connector {payload.connectorId}")
    
    # In a real system, you would generate a unique transaction ID and save it.
    transaction_id = len(TRANSACTIONS) + 1
    TRANSACTIONS[transaction_id] = {
        "charge_point_id": charge_point_id,
        "id_tag": payload.idTag,
        "start_time": payload.timestamp,
        "meter_start": payload.meterStart,
    }
    
    return StartTransactionResponse(
        transactionId=transaction_id,
        idTagInfo=IdTagInfo(status="Accepted")
    )

async def handle_stop_transaction(charge_point_id: str, payload: StopTransactionRequest) -> StopTransactionResponse:
    """Handles a StopTransaction request."""
    logger.info(f"Received StopTransaction from {charge_point_id} for transaction {payload.transactionId}")
    
    if payload.transactionId in TRANSACTIONS:
        TRANSACTIONS[payload.transactionId].update({
            "stop_time": payload.timestamp,
            "meter_stop": payload.meterStop,
            "reason": payload.reason,
        })
    
    return StopTransactionResponse(idTagInfo=IdTagInfo(status="Accepted"))

async def handle_meter_values(charge_point_id: str, payload: MeterValuesRequest) -> MeterValuesResponse:
    """Handles a MeterValues request."""
    logger.info(f"Received MeterValues from {charge_point_id} for connector {payload.connectorId}")
    for mv in payload.meterValue:
        logger.debug(f"  - Timestamp: {mv.timestamp}, Sampled Values: {mv.sampledValue}")
    return MeterValuesResponse()

# --- Handlers for responses to server-initiated commands ---

async def handle_change_availability_response(charge_point_id: str, payload: ChangeAvailabilityResponse):
    """Handles the response to a ChangeAvailability request."""
    logger.info(f"Received ChangeAvailability.conf from {charge_point_id}: {payload.status}")

async def handle_get_configuration_response(charge_point_id: str, payload: GetConfigurationResponse):
    """Handles the response to a GetConfiguration request."""
    logger.info(f"Received GetConfiguration.conf from {charge_point_id}.")
    if payload.configurationKey:
        for key in payload.configurationKey:
            logger.debug(f"  - Key: {key.key}, Readonly: {key.readonly}, Value: {key.value}")
    if payload.unknownKey:
        logger.warning(f"  - Unknown keys: {payload.unknownKey}")

async def handle_change_configuration_response(charge_point_id: str, payload: ChangeConfigurationResponse):
    """Handles the response to a ChangeConfiguration request."""
    logger.info(f"Received ChangeConfiguration.conf from {charge_point_id}: {payload.status}")

async def handle_trigger_message_response(charge_point_id: str, payload: TriggerMessageResponse):
    """Handles the response to a TriggerMessage request."""
    logger.info(f"Received TriggerMessage.conf from {charge_point_id}: {payload.status}")

async def handle_get_composite_schedule_response(charge_point_id: str, payload: GetCompositeScheduleResponse):
    """Handles the response to a GetCompositeSchedule request."""
    logger.info(f"Received GetCompositeSchedule.conf from {charge_point_id}: {payload.status}")
    if payload.status == "Accepted":
        logger.debug(f"  - Schedule: {payload.chargingSchedule}")

async def handle_clear_charging_profile_response(charge_point_id: str, payload: ClearChargingProfileResponse):
    """Handles the response to a ClearChargingProfile request."""
    logger.info(f"Received ClearChargingProfile.conf from {charge_point_id}: {payload.status}")

async def handle_set_charging_profile_response(charge_point_id: str, payload: SetChargingProfileResponse):
    """Handles the response to a SetChargingProfile request."""
    logger.info(f"Received SetChargingProfile.conf from {charge_point_id}: {payload.status}")