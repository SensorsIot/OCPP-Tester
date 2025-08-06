"""
This module contains handler functions for each of the Charge Point-initiated
OCPP messages, as specified in the provided documents.

Each handler takes a parsed message payload and the WebSocket connection
as input, performs the required server actions, and returns the appropriate
OCPP response payload.
"""
import logging
import datetime
import random
import json
from typing import Dict, Any, List

# Corrected relative imports to find modules in the same directory
from .messages import (
    BootNotificationRequest,
    BootNotificationResponse,
    AuthorizeRequest,
    AuthorizeResponse,
    DataTransferRequest,
    DataTransferResponse,
    StatusNotificationRequest,
    StatusNotificationResponse,
    FirmwareStatusNotificationRequest,
    FirmwareStatusNotificationResponse,
    DiagnosticsStatusNotificationRequest,
    DiagnosticsStatusNotificationResponse,
    GetConfigurationRequest,
    GetConfigurationResponse,
    ChangeAvailabilityResponse,
    ConfigurationKey,
    ChangeConfigurationRequest,
    ChangeConfigurationResponse,
    TriggerMessageRequest,
    TriggerMessageResponse,
    MeterValuesRequest,
    MeterValuesResponse,
    GetCompositeScheduleRequest,
    GetCompositeScheduleResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    IdTagInfo,
    StartTransactionRequest,
    StartTransactionResponse,
    StopTransactionRequest,
    StopTransactionResponse,
    MeterValue,
    SampledValue,
    # Import Smart Charging payloads
    ClearChargingProfileRequest,
    ClearChargingProfileResponse,
    SetChargingProfileRequest,
    SetChargingProfileResponse
)

# In-memory storage for Charge Point data, Authorization list, and Transactions
# This data will be reset each time the server starts.
CHARGE_POINTS: Dict[str, Dict[str, Any]] = {}
AUTHORIZATION_LIST: Dict[str, IdTagInfo] = {
    "test_id_1": IdTagInfo(status="Accepted"),
    "test_id_2": IdTagInfo(status="Accepted"),
    "test_id_3": IdTagInfo(status="Blocked"),
}
TRANSACTIONS: Dict[int, Dict[str, Any]] = {}

# Configure logging for this module
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def handle_boot_notification(charge_point_id: str, payload: BootNotificationRequest) -> BootNotificationResponse:
    """
    Handles a BootNotification.req message from a Charge Point.
    
    Server Action: Registers the Charge Point and its configuration in the in-memory store.
    
    Returns: A BootNotification.conf payload.
    """
    logger.info(f"Received BootNotification from Charge Point: {charge_point_id}")
    logger.info("--- Boot Notification Details ---")
    logger.info(f"  - Vendor: {payload.chargePointVendor}")
    logger.info(f"  - Model:  {payload.chargePointModel}")
    if payload.firmwareVersion:
        logger.info(f"  - Firmware Version: {payload.firmwareVersion}")
    if payload.chargePointSerialNumber:
        logger.info(f"  - Serial Number: {payload.chargePointSerialNumber}")
    logger.info("---------------------------------")
    # Register or update the Charge Point in our in-memory storage
    CHARGE_POINTS[charge_point_id] = {
        "chargePointModel": payload.chargePointModel,
        "chargePointVendor": payload.chargePointVendor,
        "firmwareVersion": payload.firmwareVersion,
        "status": "Booting", # Initial status
        "connectors": {} # A dictionary to store connector statuses
    }

    # Match the heartbeat interval from the original log file.
    status = "Accepted"
    heartbeat_interval = 60

    logger.debug(f"Accepted BootNotification. Setting heartbeat interval to {heartbeat_interval} seconds.")

    current_time = datetime.datetime.now(datetime.timezone.utc).isoformat() 

    return BootNotificationResponse(
        status=status,
        currentTime=current_time,
        interval=heartbeat_interval
    )

async def handle_authorize(charge_point_id: str, payload: AuthorizeRequest) -> AuthorizeResponse:
    """
    Handles an Authorize.req message from a Charge Point.
    
    Server Action: Validates the idTag against the in-memory authorization list.
    
    Returns: An Authorize.conf payload.
    """
    logger.debug(f"Received Authorize request from Charge Point {charge_point_id} for idTag: {payload.idTag}")
    logger.debug(f"Payload: {payload}")

    # Validate the idTag against our in-memory authorization list.
    id_tag_info = AUTHORIZATION_LIST.get(payload.idTag)
    
    if id_tag_info is None:
        id_tag_info = IdTagInfo(status="Invalid")
        logger.warning(f"ID Tag '{payload.idTag}' not found. Authorization rejected.")

    logger.debug(f"Authorization status for idTag {payload.idTag}: {id_tag_info.status}")

    return AuthorizeResponse(
        idTagInfo=id_tag_info
    )

async def handle_data_transfer(charge_point_id: str, payload: DataTransferRequest) -> DataTransferResponse:
    """
    Handles a DataTransfer.req message.
    
    Server Action: Receives vendor-specific data.
    
    Returns: A DataTransfer.conf payload.
    """
    logger.debug(f"Received DataTransfer from Charge Point {charge_point_id}")
    logger.debug(f"Payload: {payload}")
    
    logger.debug(f"Vendor-specific data received from vendor {payload.vendorId}: {payload.data}")

    status = "Accepted"
    
    return DataTransferResponse(
        status=status,
        data="OK"
    )

async def handle_status_notification(charge_point_id: str, payload: StatusNotificationRequest) -> StatusNotificationResponse:
    """
    Handles a StatusNotification.req message from a Charge Point.
    
    Server Action: Updates the status of the Charge Point/connector in the in-memory store.
    
    Returns: A StatusNotification.conf payload.
    """
    logger.info(f"Received StatusNotification from Charge Point {charge_point_id}")
    logger.info("--- Status Notification Details ---")
    logger.info(f"  - Connector ID: {payload.connectorId}")
    logger.info(f"  - Status:       {payload.status}")
    logger.info(f"  - Error Code:   {payload.errorCode}")
    if payload.timestamp:
        logger.info(f"  - Timestamp:    {payload.timestamp}")
    logger.info("-----------------------------------")
    if charge_point_id in CHARGE_POINTS:
        if 'connectors' not in CHARGE_POINTS[charge_point_id]:
            CHARGE_POINTS[charge_point_id]['connectors'] = {}
        
        CHARGE_POINTS[charge_point_id]['connectors'][payload.connectorId] = {
            'status': payload.status,
            'errorCode': payload.errorCode,
            'timestamp': payload.timestamp,
        }
        logger.debug(f"Updated status for connector {payload.connectorId} on {charge_point_id} to '{payload.status}'")
    
    return StatusNotificationResponse()

async def handle_firmware_status_notification(charge_point_id: str, payload: FirmwareStatusNotificationRequest) -> FirmwareStatusNotificationResponse:
    """
    Handles a FirmwareStatusNotification.req message from a Charge Point.
    
    Server Action: Logs the firmware update status of the Charge Point.
    
    Returns: A FirmwareStatusNotification.conf payload.
    """
    logger.info(f"Received FirmwareStatusNotification from {charge_point_id}: Status is '{payload.status}'")
    
    # In a real system, you would add logic here to track firmware update progress.
    
    return FirmwareStatusNotificationResponse()

async def handle_diagnostics_status_notification(charge_point_id: str, payload: DiagnosticsStatusNotificationRequest) -> DiagnosticsStatusNotificationResponse:
    """
    Handles a DiagnosticsStatusNotification.req message from a Charge Point.
    
    Server Action: Logs the diagnostics upload status of the Charge Point.
    
    Returns: A DiagnosticsStatusNotification.conf payload.
    """
    logger.info(f"Received DiagnosticsStatusNotification from {charge_point_id}: Status is '{payload.status}'")
    
    # In a real system, you would add logic here to handle the uploaded diagnostics file.
    
    return DiagnosticsStatusNotificationResponse()


async def handle_heartbeat(charge_point_id: str, payload: HeartbeatRequest) -> HeartbeatResponse:
    """
    Handles a Heartbeat.req message from a Charge Point.
    
    Server Action: Resets the Charge Point's inactivity timer and returns the current time.
    
    Returns: A Heartbeat.conf payload.
    """
    logger.debug(f"Received Heartbeat from Charge Point: {charge_point_id}")
    logger.debug(f"Payload: {payload}")
    
    current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    return HeartbeatResponse(currentTime=current_time)

# ---- Handlers for Start and Stop Transaction ----

async def handle_start_transaction(charge_point_id: str, payload: StartTransactionRequest) -> StartTransactionResponse:
    """
    Handles a StartTransaction.req message from a Charge Point.
    
    Server Action: Validates the idTag and logs the start of a new transaction in the in-memory store.
    
    Returns: A StartTransaction.conf payload.
    """
    logger.debug(f"Received StartTransaction from Charge Point {charge_point_id} for idTag: {payload.idTag}")
    logger.debug(f"Payload: {payload}")
    
    # Generate a unique transactionId
    transaction_id = random.randint(100000, 999999)
    
    # Validate the idTag
    id_tag_info = AUTHORIZATION_LIST.get(payload.idTag)
    
    if id_tag_info is None or id_tag_info.status != "Accepted":
        id_tag_info = IdTagInfo(status="Invalid")
        logger.warning(f"Authorization failed for idTag '{payload.idTag}'. Cannot start transaction.")
        # If transaction is not authorized, we should return the response and not proceed
        return StartTransactionResponse(
            idTagInfo=id_tag_info,
            transactionId=0
        )
    
    # Log the transaction in our in-memory storage
    TRANSACTIONS[transaction_id] = {
        "charge_point_id": charge_point_id,
        "connector_id": payload.connectorId,
        "id_tag": payload.idTag,
        "meter_start": payload.meterStart,
        "start_time": payload.timestamp
    }
    
    logger.debug(f"Started new transaction {transaction_id} for idTag {payload.idTag}")
    
    return StartTransactionResponse(
        idTagInfo=id_tag_info,
        transactionId=transaction_id
    )

async def handle_stop_transaction(charge_point_id: str, payload: StopTransactionRequest) -> StopTransactionResponse:
    """
    Handles a StopTransaction.req message from a Charge Point.
    
    Server Action: Logs the end of the transaction and finalizes billing data in the in-memory store.
    
    Returns: a StopTransaction.conf payload.
    """
    logger.debug(f"Received StopTransaction from Charge Point {charge_point_id} for transactionId: {payload.transactionId}")
    logger.debug(f"Payload: {payload}")
    
    # Check if the transaction exists and update it
    if payload.transactionId in TRANSACTIONS:
        TRANSACTIONS[payload.transactionId].update({
            "meter_stop": payload.meterStop,
            "stop_time": payload.timestamp,
            "reason": payload.reason,
            "transaction_data": payload.transactionData,
        })
        logger.debug(f"Stopped transaction {payload.transactionId}. Final meter reading: {payload.meterStop}")
        
    # Return a response with the idTagInfo if provided
    id_tag_info = AUTHORIZATION_LIST.get(payload.idTag) if payload.idTag in AUTHORIZATION_LIST else None

    return StopTransactionResponse(idTagInfo=id_tag_info)


# ---- Handlers for server-initiated replies ----

async def handle_change_availability_response(charge_point_id: str, payload: ChangeAvailabilityResponse) -> None:
    """
    Handles a ChangeAvailability.conf message from a Charge Point.
    """
    logger.debug(f"Received ChangeAvailability.conf from Charge Point: {charge_point_id} with status: {payload.status}")
    logger.debug(f"Payload: {payload}")


async def handle_get_configuration_response(charge_point_id: str, payload: GetConfigurationResponse) -> None:
    """
    Handles a GetConfiguration.conf message from a Charge Point.
    """
    logger.info(f"Received GetConfiguration.conf from Charge Point: {charge_point_id}")

    if payload.configurationKey:
        logger.info("--- Received Charge Point Configuration ---")
        # Pretty print the configuration key-value pairs
        for key_value in payload.configurationKey:
            # Truncate long values for cleaner log output, as some values can be very long.
            display_value = str(key_value.value)
            if len(display_value) > 55:
                display_value = display_value[:52] + "..."
            
            # The key_value is a ConfigurationKey object thanks to the __post_init__ in the message class
            logger.info(f"  - {key_value.key:<45} | Value: {display_value:<55} | Readonly: {key_value.readonly}")
        logger.info("-------------------------------------------")

    if payload.unknownKey:
        logger.warning("--- Received Unknown Configuration Keys ---")
        for key in payload.unknownKey:
            logger.warning(f"  - {key}")
        logger.warning("-------------------------------------------")

async def handle_change_configuration_response(charge_point_id: str, payload: ChangeConfigurationResponse) -> None:
    """
    Handles a ChangeConfiguration.conf message from a Charge Point.
    """
    logger.debug(f"Received ChangeConfiguration.conf from Charge Point: {charge_point_id} with status: {payload.status}")
    logger.debug(f"Payload: {payload}")

async def handle_trigger_message_response(charge_point_id: str, payload: TriggerMessageResponse) -> None:
    """
    Handles a TriggerMessage.conf message from a Charge Point.
    """
    logger.debug(f"Received TriggerMessage.conf from Charge Point: {charge_point_id} with status: {payload.status}")
    logger.debug(f"Payload: {payload}")

async def handle_meter_values(charge_point_id: str, payload: MeterValuesRequest) -> MeterValuesResponse:
    """
    Handles a MeterValues.req message from a Charge Point.
    
    This has been updated to correctly parse the nested MeterValue and
    SampledValue objects from the raw dictionaries.
    """
    logger.info(f"Received MeterValues from Charge Point {charge_point_id} for connector {payload.connectorId}")
    logger.info("--- Meter Values Details ---")
    if payload.transactionId:
        logger.info(f"  - Transaction ID: {payload.transactionId}")
    
    # The payload.meterValue is a list of MeterValue objects thanks to the __post_init__ in the message class.
    for meter_value in payload.meterValue:
        logger.info(f"  - Timestamp: {meter_value.timestamp}")
        
        # The meter_value.sampledValue is a list of SampledValue objects.
        for sampled_value in meter_value.sampledValue:
            unit = f" {sampled_value.unit}" if sampled_value.unit else ""
            logger.info(f"    - {sampled_value.measurand:<30} | Value: {sampled_value.value}{unit}")
    logger.info("----------------------------")
            
    return MeterValuesResponse()

async def handle_get_composite_schedule_response(charge_point_id: str, payload: GetCompositeScheduleResponse) -> None:
    """
    Handles a GetCompositeSchedule.conf message from a Charge Point.
    """
    logger.info(f"Received GetCompositeSchedule.conf from Charge Point: {charge_point_id}")
    logger.info("--- Composite Schedule Details ---")
    logger.info(f"  - Status: {payload.status}")

    if payload.status == "Accepted" and payload.chargingSchedule:
        logger.info(f"  - Connector ID: {payload.connectorId}")
        logger.info(f"  - Schedule Start: {payload.scheduleStart}")
        schedule = payload.chargingSchedule
        logger.info(f"  - Charging Schedule:")
        logger.info(f"    - Rate Unit: {schedule.chargingRateUnit}")
        if schedule.duration:
            logger.info(f"    - Duration (s): {schedule.duration}")
        if schedule.minChargingRate:
            logger.info(f"    - Min Rate: {schedule.minChargingRate}")
        
        logger.info("    - Schedule Periods:")
        for period in schedule.chargingSchedulePeriod:
            logger.info(f"      - Start: {period.startPeriod}s, Limit: {period.limit} {schedule.chargingRateUnit}")

    logger.info("----------------------------------")

# === NEW: Handler for SetChargingProfile response ===
async def handle_set_charging_profile_response(charge_point_id: str, payload: SetChargingProfileResponse) -> None:
    """
    Handles a SetChargingProfile.conf message from a Charge Point.
    """
    logger.info(f"Received SetChargingProfile.conf from Charge Point: {charge_point_id} with status: {payload.status}")
    logger.info(f"Payload: {payload}")

# === NEW: Handler for ClearChargingProfile response ===
async def handle_clear_charging_profile_response(charge_point_id: str, payload: ClearChargingProfileResponse) -> None:
    """
    Handles a ClearChargingProfile.conf message from a Charge Point.
    """
    logger.info(f"Received ClearChargingProfile.conf from Charge Point: {charge_point_id} with status: {payload.status}")
    logger.info(f"Payload: {payload}")