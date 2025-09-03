import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict
from dataclasses import asdict

from app.core import CHARGE_POINTS, TRANSACTIONS, SERVER_SETTINGS, get_active_transaction_id, set_active_transaction_id
from app.messages import (
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
)

if TYPE_CHECKING:
    from app.ocpp_server_logic import OcppServerLogic

logger = logging.getLogger(__name__)

VALID_ID_TAGS = ["test_id_1", "test_id_2"]
CP_STATE_MAP = {
    "Available": "CP State A",
    "Preparing": "CP State B",
    "Charging": "CP State C",
    "Finishing": "CP State X",
    "Faulted": "CP State E",
}

class OcppMessageHandlers:
    def __init__(self, ocpp_server_logic: "OcppServerLogic"):
        self.ocpp_server_logic = ocpp_server_logic
        self.handler = ocpp_server_logic.handler
        self.charge_point_id = ocpp_server_logic.charge_point_id
        self.pending_triggered_message_events = ocpp_server_logic.pending_triggered_message_events
        self.initial_status_received = ocpp_server_logic.initial_status_received

    async def handle_boot_notification(self, charge_point_id: str, payload: BootNotificationRequest) -> BootNotificationResponse:
        if "BootNotification" in self.pending_triggered_message_events:
            logger.info("Detected a triggered BootNotification message, setting event.")
            self.pending_triggered_message_events["BootNotification"].set()
            
        logger.info(f"Received BootNotification from {charge_point_id}: {payload}")
        if charge_point_id not in CHARGE_POINTS:
            CHARGE_POINTS[charge_point_id] = {}
        CHARGE_POINTS[charge_point_id].update({
            "model": payload.chargePointModel,
            "vendor": payload.chargePointVendor,
            "status": "Available",
            "last_heartbeat": datetime.now(timezone.utc).isoformat()
        })
        if self.initial_status_received and not self.initial_status_received.is_set():
            self.initial_status_received.set()

        return BootNotificationResponse(
            status="Accepted",
            currentTime=datetime.now(timezone.utc).isoformat(),
            interval=60
        )

    async def handle_authorize(self, charge_point_id: str, payload: AuthorizeRequest) -> AuthorizeResponse:
        logger.info(f"Received Authorize request from {charge_point_id} for idTag: {payload.idTag}")
        status = "Accepted" if payload.idTag in VALID_ID_TAGS else "Invalid"
        return AuthorizeResponse(idTagInfo=IdTagInfo(status=status))

    async def handle_data_transfer(self, charge_point_id: str, payload: DataTransferRequest) -> DataTransferResponse:
        logger.info(f"Received DataTransfer from {charge_point_id}: {payload}")
        return DataTransferResponse(status="Accepted")

    async def handle_status_notification(self, charge_point_id: str, payload: StatusNotificationRequest) -> StatusNotificationResponse:
        if "StatusNotification" in self.pending_triggered_message_events:
            logger.info("Detected a triggered StatusNotification message, setting event.")
            self.pending_triggered_message_events["StatusNotification"].set()

        logger.debug(f"Handling StatusNotification from {charge_point_id}: {payload.status}")
        cp_state_log_message = f" (equivalent to {CP_STATE_MAP.get(payload.status, 'Unknown')})"
        logger.info(f"Received StatusNotification from {charge_point_id}: Connector {payload.connectorId} is {payload.status}{cp_state_log_message}")
        if charge_point_id in CHARGE_POINTS:
            CHARGE_POINTS[charge_point_id]["status"] = payload.status

        if self.initial_status_received and not self.initial_status_received.is_set():
            self.initial_status_received.set()

        # Only trigger a refresh of the EV simulator panel if it's in use.
        if self.ocpp_server_logic.refresh_trigger and SERVER_SETTINGS.get("ev_simulator_available"):
            # The UI polls the EV simulator status. If the CP status changes,
            # it might be useful to trigger a faster refresh of the simulator state for the UI.
            logger.debug("CP status changed, setting EV refresh trigger for UI.")
            self.ocpp_server_logic.refresh_trigger.set()
        return StatusNotificationResponse()

    async def handle_firmware_status_notification(self, charge_point_id: str, payload: FirmwareStatusNotificationRequest) -> FirmwareStatusNotificationResponse:
        if "FirmwareStatusNotification" in self.pending_triggered_message_events:
            logger.info("Detected a triggered FirmwareStatusNotification message, setting event.")
            self.pending_triggered_message_events["FirmwareStatusNotification"].set()

        logger.info(f"Received FirmwareStatusNotification from {charge_point_id}: {payload.status}")
        return FirmwareStatusNotificationResponse()

    async def handle_diagnostics_status_notification(self, charge_point_id: str, payload: DiagnosticsStatusNotificationRequest) -> DiagnosticsStatusNotificationResponse:
        if "DiagnosticsStatusNotification" in self.pending_triggered_message_events:
            logger.info("Detected a triggered DiagnosticsStatusNotification message, setting event.")
            self.pending_triggered_message_events["DiagnosticsStatusNotification"].set()

        logger.info(f"Received DiagnosticsStatusNotification from {charge_point_id}: {payload.status}")
        return DiagnosticsStatusNotificationResponse()

    async def handle_heartbeat(self, charge_point_id: str, payload: HeartbeatRequest) -> HeartbeatResponse:
        if "Heartbeat" in self.pending_triggered_message_events:
            logger.info("Detected a triggered Heartbeat message, setting event.")
            self.pending_triggered_message_events["Heartbeat"].set()

        logger.info(f"Received Heartbeat from {charge_point_id}")
        if charge_point_id in CHARGE_POINTS:
            CHARGE_POINTS[charge_point_id]["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
        return HeartbeatResponse(currentTime=datetime.now(timezone.utc).isoformat())

    async def handle_start_transaction(self, charge_point_id: str, payload: StartTransactionRequest) -> StartTransactionResponse:
        logger.info(f"Received StartTransaction from {charge_point_id}: {payload}. CP Transaction ID: {payload.transactionId}")

        # The wallbox's transactionId is now available in the payload.
        cp_transaction_id = payload.transactionId

        # Generate a new internal transaction ID for the StartTransactionResponse.
        # This is the ID the Central System will use to refer to this transaction.
        cs_internal_transaction_id = len(TRANSACTIONS) + 1 # Use a new internal ID for the response

        # Check if this is a confirmation of a remotely started transaction.
        # We look for a pending remote start based on charge_point_id and connectorId.
        existing_transaction_data = None
        for key, t_data in TRANSACTIONS.items():
            if t_data.get("charge_point_id") == charge_point_id and \
               t_data.get("connector_id") == payload.connectorId and \
               t_data.get("remote_started") is True and \
               t_data.get("status") == "Ongoing":
                existing_transaction_data = t_data
                # Update the key in TRANSACTIONS to use the CP's transactionId
                # This is important for subsequent MeterValues/StopTransaction messages
                # that will use the CP's transactionId as the key.
                TRANSACTIONS[cp_transaction_id] = TRANSACTIONS.pop(key)
                break

        if existing_transaction_data:
            # This is a confirmation of a remotely started transaction.
            # Update the existing transaction record with the CP's transactionId.
            existing_transaction_data.update({
                "start_time": payload.timestamp,
                "meter_start": payload.meterStart,
                "remote_started": False, # Mark it as confirmed by StartTransaction
                "cp_transaction_id": cp_transaction_id, # Store the CP's transaction ID
                "cs_internal_transaction_id": cs_internal_transaction_id # Store the CS's internal ID
            })
            logger.info(f"Updated existing remotely started transaction (CP ID: {cp_transaction_id}) with StartTransaction data.")
            transaction_id_to_return = cs_internal_transaction_id
        else:
            # This is a new transaction initiated by the Charge Point.
            # Store it directly with the CP's transactionId as the key.
            TRANSACTIONS[cp_transaction_id] = {
                "charge_point_id": charge_point_id,
                "id_tag": payload.idTag,
                "start_time": payload.timestamp,
                "meter_start": payload.meterStart,
                "connector_id": payload.connectorId,
                "status": "Ongoing",
                "remote_started": False, # This transaction was initiated by CP, not remotely by us
                "cp_transaction_id": cp_transaction_id, # Store the CP's transaction ID
                "cs_internal_transaction_id": cs_internal_transaction_id # Store the CS's internal ID
            }
            logger.info(f"Created new transaction (CP ID: {cp_transaction_id}) initiated by CP.")
            transaction_id_to_return = cs_internal_transaction_id

        set_active_transaction_id(cp_transaction_id) # Update the global active transaction ID with CP's ID
        return StartTransactionResponse(
            transactionId=transaction_id_to_return,
            idTagInfo=IdTagInfo(status="Accepted")
        )

    async def handle_stop_transaction(self, charge_point_id: str, payload: StopTransactionRequest) -> StopTransactionResponse:
        logger.info(f"Received StopTransaction from {charge_point_id}: {payload}")
        
        # Try to find the transaction using the CP's transactionId as the key
        transaction_data = TRANSACTIONS.get(payload.transactionId)

        if transaction_data:
            # Found by CP's transactionId
            logger.debug(f"Found transaction {payload.transactionId} by its CP ID for StopTransaction.")
            
            transaction_data.update({
                "stop_time": payload.timestamp,
                "meter_stop": payload.meterStop,
                "status": "Completed",
                "reason": payload.reason
            })
            # Ensure cp_transaction_id is set (it should be, but for safety)
            if transaction_data.get("cp_transaction_id") is None:
                transaction_data["cp_transaction_id"] = payload.transactionId

            # Remove the transaction from the TRANSACTIONS dictionary
            del TRANSACTIONS[payload.transactionId]
            logger.info(f"Transaction {payload.transactionId} removed from active transactions.")

            # Clear the active transaction ID
            set_active_transaction_id(None)
            await asyncio.sleep(0.1) # Add a small delay
            return StopTransactionResponse()
        else:
            logger.info(f"StopTransaction received for transaction (CP ID: {payload.transactionId}) not found in active records. Acknowledging stop.")
            # Clear the active transaction ID even if not found, as the transaction is ending from CP\'s perspective
            set_active_transaction_id(None) 
            await asyncio.sleep(0.1) # Add a small delay
            return StopTransactionResponse() # Still send a response even if not found internally

    async def handle_meter_values(self, charge_point_id: str, payload: MeterValuesRequest) -> MeterValuesResponse:
        # Check if this was a triggered message we were waiting for
        if "MeterValues" in self.pending_triggered_message_events:
            # The context should be 'Trigger' if it was triggered.
            is_triggered = any(
                sv.context == "Trigger" for mv in payload.meterValue for sv in mv.sampledValue
            )
            if is_triggered:
                logger.info("Detected a triggered MeterValues message, setting event.")
                self.pending_triggered_message_events["MeterValues"].set()

        logger.info(f"Received MeterValues from {charge_point_id} for connector {payload.connectorId}. Entire Payload: {asdict(payload)}")
        
        if payload.transactionId is not None:
            logger.info(f"Extracting transaction ID from MeterValues.req: {payload.transactionId}")
            # Find the transaction using the CP's transactionId as the key
            transaction_data = TRANSACTIONS.get(payload.transactionId)

            if transaction_data:
                # Found by CP's transactionId
                logger.debug(f"Found transaction {payload.transactionId} by its CP ID.")
                
                # Ensure cp_transaction_id is set (it should be, but for safety)
                if transaction_data.get("cp_transaction_id") is None:
                    transaction_data["cp_transaction_id"] = payload.transactionId
                
                if "meter_values" not in transaction_data:
                    transaction_data["meter_values"] = []
                transaction_data["meter_values"].extend(payload.meterValue)
                set_active_transaction_id(payload.transactionId)

            else:
                # Transaction not found, create a new entry based on MeterValues.
                logger.info(f"Information: MeterValues received a new transaction id {payload.transactionId}. It started a new transaction.")
                TRANSACTIONS[payload.transactionId] = {
                    "charge_point_id": charge_point_id,
                    "id_tag": "unknown", # idTag is not available in MeterValues.req
                    "start_time": payload.meterValue[0].timestamp if payload.meterValue else datetime.now(timezone.utc).isoformat(),
                    "meter_start": payload.meterValue[0].sampledValue[0].value if payload.meterValue and payload.meterValue[0].sampledValue else 0,
                    "connector_id": payload.connectorId,
                    "status": "Ongoing",
                    "remote_started": False, # This transaction was initiated by CP, not remotely by us
                    "cp_transaction_id": payload.transactionId, # Store the CP's transaction ID
                    "cs_internal_transaction_id": None # CS internal ID not known from MeterValues
                }
                if "meter_values" not in TRANSACTIONS[payload.transactionId]:
                    TRANSACTIONS[payload.transactionId]["meter_values"] = []
                TRANSACTIONS[payload.transactionId]["meter_values"].extend(payload.meterValue)
                set_active_transaction_id(payload.transactionId)
        else:
            logger.warning(f"MeterValues received from {charge_point_id} without a transaction ID. Cannot associate with a specific transaction.")

        for mv in payload.meterValue:
            logger.debug(f"  -> Timestamp: {mv.timestamp}")
            for sv in mv.sampledValue:
                unit = f" {sv.unit}" if sv.unit else ""
                measurand = sv.measurand or "N/A"

                details_parts = []
                if sv.context: details_parts.append(f"context: {sv.context}")
                if sv.location: details_parts.append(f"location: {sv.location}")
                if sv.phase: details_parts.append(f"phase: {sv.phase}")
                details = f" ({', '.join(details_parts)})" if details_parts else ""

                log_message = f"    - {measurand}: {sv.value}{unit}{details}"
                logger.info(log_message)
            
        return MeterValuesResponse()

    async def handle_unknown_action(self, charge_point_id: str, payload: dict):
        logger.warning(f"Unknown/unsupported action for {charge_point_id}: {payload}")
        return None
