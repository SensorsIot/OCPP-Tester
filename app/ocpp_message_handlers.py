import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict

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
        logger.info(f"Received StartTransaction from {charge_point_id}: {payload}")

        # Generate a new internal transaction ID.
        internal_transaction_id = len(TRANSACTIONS) + 1

        # Check if this is a confirmation of a remotely started transaction.
        existing_remote_started_transaction_id = None
        for tid, tdata in TRANSACTIONS.items():
            if tdata.get("charge_point_id") == charge_point_id and \
               tdata.get("connector_id") == payload.connectorId and \
               tdata.get("id_tag") == payload.idTag and \
               tdata.get("remote_started") is True and \
               tdata.get("status") == "Ongoing":
                existing_remote_started_transaction_id = tid
                break

        if existing_remote_started_transaction_id:
            # This is a confirmation of a remotely started transaction.
            # Update the existing transaction record.
            TRANSACTIONS[existing_remote_started_transaction_id].update({
                "start_time": payload.timestamp,
                "meter_start": payload.meterStart,
                "remote_started": False, # Mark it as confirmed by StartTransaction
                "cp_transaction_id": payload.transactionId # Store CP's transactionId
            })
            logger.info(f"Updated existing remotely started transaction {existing_remote_started_transaction_id} with StartTransaction data.")
            transaction_id_to_return = existing_remote_started_transaction_id
        else:
            # This is a new transaction initiated by the Charge Point.
            TRANSACTIONS[internal_transaction_id] = {
                "charge_point_id": charge_point_id,
                "id_tag": payload.idTag,
                "start_time": payload.timestamp,
                "meter_start": payload.meterStart,
                "connector_id": payload.connectorId,
                "status": "Ongoing",
                "remote_started": False # This transaction was initiated by CP, not remotely by us
            }
            logger.info(f"Created new transaction {internal_transaction_id} initiated by CP.")
            transaction_id_to_return = internal_transaction_id

        return StartTransactionResponse(
            transactionId=transaction_id_to_return,
            idTagInfo=IdTagInfo(status="Accepted")
        )

    async def handle_stop_transaction(self, charge_point_id: str, payload: StopTransactionRequest) -> StopTransactionResponse:
        logger.info(f"Received StopTransaction from {charge_point_id}: {payload}")
        # Update the active transaction ID with the one from the StopTransaction payload
        set_active_transaction_id(payload.transactionId)
        # Find the transaction using the CP's transactionId
        found_internal_transaction_id = None
        for internal_tid, tdata in TRANSACTIONS.items():
            if tdata.get("charge_point_id") == charge_point_id and \
               tdata.get("status") == "Ongoing" and \
               tdata.get("cp_transaction_id") == payload.transactionId: # Match by CP's transactionId
                found_internal_transaction_id = internal_tid
                break

        if found_internal_transaction_id:
            # Store the CP's transactionId if not already set
            if TRANSACTIONS[found_internal_transaction_id].get("cp_transaction_id") is None:
                TRANSACTIONS[found_internal_transaction_id]["cp_transaction_id"] = payload.transactionId
            
            TRANSACTIONS[found_internal_transaction_id].update({
                "stop_time": payload.timestamp,
                "meter_stop": payload.meterStop,
                "status": "Completed",
                "reason": payload.reason
            })
            # Clear the active transaction ID
            set_active_transaction_id(None)
            return StopTransactionResponse()
        else:
            logger.warning(f"StopTransaction received for unknown or non-ongoing transaction (CP ID: {payload.transactionId}).")
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

        logger.debug(f"Received MeterValues from {charge_point_id} for connector {payload.connectorId} (transactionId: {payload.transactionId})")
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
                # Highlight the offered current from the wallbox itself
                if measurand == "Current.Offered":
                    logger.info(log_message)
                else:
                    logger.debug(log_message)
        # Find the transaction using the CP's transactionId
        found_internal_transaction_id = None
        for internal_tid, tdata in TRANSACTIONS.items():
            logger.debug(f"Checking transaction {internal_tid}: CP ID={tdata.get('charge_point_id')}, Status={tdata.get('status')}, CP_Tx_ID={tdata.get('cp_transaction_id')}. Payload Tx ID={payload.transactionId}")
            # Match by charge_point_id and status, and if cp_transaction_id is not set yet, or matches
            if tdata.get("charge_point_id") == charge_point_id and \
               tdata.get("status") == "Ongoing" and \
               (tdata.get("cp_transaction_id") is None or tdata.get("cp_transaction_id") == payload.transactionId):
                found_internal_transaction_id = internal_tid
                break

        if found_internal_transaction_id:
            # Store the CP's transactionId if not already set
            if TRANSACTIONS[found_internal_transaction_id].get("cp_transaction_id") is None:
                TRANSACTIONS[found_internal_transaction_id]["cp_transaction_id"] = payload.transactionId
            
            if "meter_values" not in TRANSACTIONS[found_internal_transaction_id]:
                TRANSACTIONS[found_internal_transaction_id]["meter_values"] = []
            TRANSACTIONS[found_internal_transaction_id]["meter_values"].extend(payload.meterValue)

            # Set the active transaction ID
            set_active_transaction_id(payload.transactionId)
        else:
            # Transaction not found as ongoing, or not found at all.
            # Attempt to find it by cp_transaction_id if it exists but is not ongoing.
            # Or create a new one if it's completely unknown.
            found_by_cp_tx_id = None
            for internal_tid, tdata in TRANSACTIONS.items():
                if tdata.get("charge_point_id") == charge_point_id and \
                   tdata.get("cp_transaction_id") == payload.transactionId:
                    found_by_cp_tx_id = internal_tid
                    break

            if found_by_cp_tx_id:
                # Found an existing transaction record, but it wasn't marked as "Ongoing".
                # Update its status to "Ongoing" and add meter values.
                TRANSACTIONS[found_by_cp_tx_id].update({
                    "status": "Ongoing",
                    "cp_transaction_id": payload.transactionId # Ensure it's set
                })
                if "meter_values" not in TRANSACTIONS[found_by_cp_tx_id]:
                    TRANSACTIONS[found_by_cp_tx_id]["meter_values"] = []
                TRANSACTIONS[found_by_cp_tx_id]["meter_values"].extend(payload.meterValue)
                logger.info(f"Discovered and updated transaction {found_by_cp_tx_id} from MeterValues.")
                set_active_transaction_id(payload.transactionId)
            else:
                # Completely new transaction, create a new entry.
                new_internal_transaction_id = len(TRANSACTIONS) + 1
                TRANSACTIONS[new_internal_transaction_id] = {
                    "charge_point_id": charge_point_id,
                    "id_tag": "unknown", # We don't have idTag from MeterValues
                    "start_time": datetime.now(timezone.utc).isoformat(),
                    "meter_start": payload.meterValue[0].sampledValue[0].value if payload.meterValue else 0, # Use first meter value as start
                    "connector_id": payload.connectorId,
                    "status": "Ongoing",
                    "cp_transaction_id": payload.transactionId
                }
                if "meter_values" not in TRANSACTIONS[new_internal_transaction_id]:
                    TRANSACTIONS[new_internal_transaction_id]["meter_values"] = []
                TRANSACTIONS[new_internal_transaction_id]["meter_values"].extend(payload.meterValue)
                logger.info(f"Discovered and created new transaction {new_internal_transaction_id} from MeterValues.")
                set_active_transaction_id(payload.transactionId)
        return MeterValuesResponse()

    async def handle_unknown_action(self, charge_point_id: str, payload: dict):
        logger.warning(f"Unknown/unsupported action for {charge_point_id}: {payload}")
        return None
