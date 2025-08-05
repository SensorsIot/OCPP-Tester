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
    GetConfigurationRequest,
    GetConfigurationResponse,
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
    MeterValue,  # Import MeterValue for proper instantiation
    SampledValue # Import SampledValue for proper instantiation
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
    logger.debug(f"Received BootNotification from Charge Point: {charge_point_id}")
    logger.debug(f"Payload: {payload}")

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
    logger.debug(f"Received StatusNotification from Charge Point {charge_point_id}")
    logger.debug(f"Payload: {payload}")
    
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

async def handle_get_configuration_response(charge_point_id: str, payload: GetConfigurationResponse) -> None:
    """
    Handles a GetConfiguration.conf message from a Charge Point.
    """
    logger.debug(f"Received GetConfiguration.conf from Charge Point: {charge_point_id}")
    logger.debug(f"Payload: {payload}")

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
    logger.debug(f"Received MeterValues from Charge Point {charge_point_id} for transaction {payload.transactionId}")
    
    # The payload.meterValue is a list of MeterValue objects.
    # We need to iterate through them to access the attributes.
    for meter_value_dict in payload.meterValue:
        # Instantiate MeterValue from the dictionary
        meter_value = MeterValue(**meter_value_dict)
        logger.debug(f"  Timestamp: {meter_value.timestamp}")
        
        # The meter_value.sampledValue is a list of SampledValue objects.
        # We need to instantiate each one from its dictionary representation.
        for sampled_value_dict in meter_value.sampledValue:
            sampled_value = SampledValue(**sampled_value_dict)
            logger.debug(f"    - Measurand: {sampled_value.measurand}, Value: {sampled_value.value} {sampled_value.unit}")
            
    return MeterValuesResponse()

async def handle_get_composite_schedule_response(charge_point_id: str, payload: GetCompositeScheduleResponse) -> None:
    """
    Handles a GetCompositeSchedule.conf message from a Charge Point.
    """
    logger.debug(f"Received GetCompositeSchedule.conf from Charge Point: {charge_point_id}")
    logger.debug(f"Payload: {payload}")

    if payload.status == "Accepted":
        logger.debug(f"Schedule start: {payload.scheduleStart}")
