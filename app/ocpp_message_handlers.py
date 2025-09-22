import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict
from dataclasses import asdict

from app.core import CHARGE_POINTS, TRANSACTIONS, SERVER_SETTINGS, get_active_transaction_id, set_active_transaction_id, auto_detect_charging_rate_unit
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
    GetConfigurationRequest,
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
        logger.debug(f"🥾 BOOT NOTIFICATION HANDLER called for {charge_point_id}")

        if "BootNotification" in self.pending_triggered_message_events:
            logger.debug("📍 Detected a triggered BootNotification message, setting event.")
            self.pending_triggered_message_events["BootNotification"].set()

        logger.info(f"🔌 Received BootNotification from {charge_point_id}: {payload}")
        logger.debug(f"🔍 Vendor: {payload.chargePointVendor}, Model: {payload.chargePointModel}")

        if charge_point_id not in CHARGE_POINTS:
            logger.debug(f"📋 Creating new entry for charge point {charge_point_id}")
            CHARGE_POINTS[charge_point_id] = {}
        else:
            logger.debug(f"📋 Updating existing entry for charge point {charge_point_id}")
        boot_time = datetime.now(timezone.utc).isoformat()
        CHARGE_POINTS[charge_point_id].update({
            "model": payload.chargePointModel,
            "vendor": payload.chargePointVendor,
            "status": "Available",
            "boot_time": boot_time,
            "last_heartbeat": boot_time
        })
        if self.initial_status_received and not self.initial_status_received.is_set():
            self.initial_status_received.set()

        # Auto-detection will be handled by StatusNotification only

        return BootNotificationResponse(
            status="Accepted",
            currentTime=datetime.now(timezone.utc).isoformat(),
            interval=60
        )

    async def handle_authorize(self, charge_point_id: str, payload: AuthorizeRequest) -> AuthorizeResponse:
        logger.info(f"📡 OCPP: Authorize request from {charge_point_id} for idTag: {payload.idTag}")
        status = "Accepted" if payload.idTag in VALID_ID_TAGS else "Invalid"
        logger.info(f"    ✅ Authorization {status} for idTag: {payload.idTag}")
        return AuthorizeResponse(idTagInfo=IdTagInfo(status=status))

    async def handle_data_transfer(self, charge_point_id: str, payload: DataTransferRequest) -> DataTransferResponse:
        logger.debug(f"Received DataTransfer from {charge_point_id}: {payload}")
        return DataTransferResponse(status="Accepted")

    async def handle_status_notification(self, charge_point_id: str, payload: StatusNotificationRequest) -> StatusNotificationResponse:
        if "StatusNotification" in self.pending_triggered_message_events:
            logger.debug("Detected a triggered StatusNotification message, setting event.")
            self.pending_triggered_message_events["StatusNotification"].set()

        logger.debug(f"📡 OCPP: StatusNotification from {charge_point_id}: {payload.status}")
        cp_state_log_message = f" (equivalent to {CP_STATE_MAP.get(payload.status, 'Unknown')})"
        logger.debug(f"Received StatusNotification from {charge_point_id}: Connector {payload.connectorId} is {payload.status}{cp_state_log_message}")
        if charge_point_id in CHARGE_POINTS:
            CHARGE_POINTS[charge_point_id]["status"] = payload.status

            # Capture the first StatusNotification timestamp from the charge point
            # This is more accurate than server-side boot time as it comes from the device itself
            if payload.timestamp and "first_status_time" not in CHARGE_POINTS[charge_point_id]:
                CHARGE_POINTS[charge_point_id]["first_status_time"] = payload.timestamp
                logger.info(f"📅 Captured first StatusNotification timestamp from {charge_point_id}: {payload.timestamp}")

        # Trigger auto-detection ONCE on first StatusNotification only
        is_first_status = self.initial_status_received and not self.initial_status_received.is_set()
        if (is_first_status and
            not SERVER_SETTINGS.get("auto_detection_completed", False) and
            "auto_detection_triggered" not in CHARGE_POINTS[charge_point_id]):
            logger.info("🔍 Triggering GetConfiguration for auto-detection (fire-and-forget) on FIRST StatusNotification...")
            # Mark that we've triggered auto-detection for this charge point
            CHARGE_POINTS[charge_point_id]["auto_detection_triggered"] = True
            asyncio.create_task(self._trigger_get_configuration())

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
            logger.debug("Detected a triggered FirmwareStatusNotification message, setting event.")
            self.pending_triggered_message_events["FirmwareStatusNotification"].set()

        logger.debug(f"Received FirmwareStatusNotification from {charge_point_id}: {payload.status}")
        return FirmwareStatusNotificationResponse()

    async def handle_diagnostics_status_notification(self, charge_point_id: str, payload: DiagnosticsStatusNotificationRequest) -> DiagnosticsStatusNotificationResponse:
        if "DiagnosticsStatusNotification" in self.pending_triggered_message_events:
            logger.debug("Detected a triggered DiagnosticsStatusNotification message, setting event.")
            self.pending_triggered_message_events["DiagnosticsStatusNotification"].set()

        logger.debug(f"Received DiagnosticsStatusNotification from {charge_point_id}: {payload.status}")
        return DiagnosticsStatusNotificationResponse()

    async def handle_heartbeat(self, charge_point_id: str, payload: HeartbeatRequest) -> HeartbeatResponse:
        if "Heartbeat" in self.pending_triggered_message_events:
            logger.debug("Detected a triggered Heartbeat message, setting event.")
            self.pending_triggered_message_events["Heartbeat"].set()

        logger.debug(f"Received Heartbeat from {charge_point_id}")
        if charge_point_id in CHARGE_POINTS:
            CHARGE_POINTS[charge_point_id]["last_heartbeat"] = datetime.now(timezone.utc).isoformat()


        return HeartbeatResponse(currentTime=datetime.now(timezone.utc).isoformat())

    async def handle_start_transaction(self, charge_point_id: str, payload: StartTransactionRequest) -> StartTransactionResponse:
        logger.info(f"📡 OCPP: StartTransaction from {charge_point_id}: {payload}")

        # In OCPP 1.6, the Central System assigns the transaction ID in StartTransaction.conf
        # The charge point will use this ID in subsequent MeterValues and StopTransaction messages
        # Generate a realistic transaction ID using timestamp + random component for uniqueness
        base_id = int(time.time() * 1000) % 1000000  # Last 6 digits of timestamp in ms
        random_component = random.randint(1000, 9999)  # 4-digit random number
        transaction_id = base_id * 10000 + random_component  # Combine for unique ID

        # Check if this is a confirmation of a remotely started transaction.
        # We look for a pending remote start based on charge_point_id and connectorId.
        existing_transaction_data = None
        for key, t_data in TRANSACTIONS.items():
            if t_data.get("charge_point_id") == charge_point_id and \
               t_data.get("connector_id") == payload.connectorId and \
               t_data.get("remote_started") is True and \
               t_data.get("status") == "Ongoing":
                existing_transaction_data = t_data
                # Update the key in TRANSACTIONS to use the assigned transaction ID
                # This is important for subsequent MeterValues/StopTransaction messages
                # that will use this transaction ID as the key.
                TRANSACTIONS[transaction_id] = TRANSACTIONS.pop(key)
                break

        if existing_transaction_data:
            # This is a confirmation of a remotely started transaction.
            # Update the existing transaction record with the assigned transaction ID.
            existing_transaction_data.update({
                "start_time": payload.timestamp,
                "meter_start": payload.meterStart,
                "remote_started": False, # Mark it as confirmed by StartTransaction
                "transaction_id": transaction_id # Store the assigned transaction ID
            })
            logger.info(f"✅ OCPP: Confirmed remote transaction (CS assigned ID: {transaction_id}) with StartTransaction data.")
            transaction_id_to_return = transaction_id
        else:
            # This is a new transaction initiated by the Charge Point.
            # Store it with the assigned transaction ID as the key.
            TRANSACTIONS[transaction_id] = {
                "charge_point_id": charge_point_id,
                "id_tag": payload.idTag,
                "start_time": payload.timestamp,
                "meter_start": payload.meterStart,
                "connector_id": payload.connectorId,
                "status": "Ongoing",
                "remote_started": False, # This transaction was initiated by CP, not remotely by us
                "transaction_id": transaction_id # Store the assigned transaction ID
            }
            logger.info(f"💫 OCPP: Created new transaction (ID: {transaction_id}) initiated by CP.")
            transaction_id_to_return = transaction_id

        set_active_transaction_id(transaction_id) # Update the global active transaction ID
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
                logger.debug("Detected a triggered MeterValues message, setting event.")
                self.pending_triggered_message_events["MeterValues"].set()

        logger.debug(f"Received MeterValues from {charge_point_id} for connector {payload.connectorId}")
        
        # Auto-detection will be handled by unsolicited GetConfiguration response processing
        # to avoid blocking the message processing loop

        if payload.transactionId is not None:
            logger.debug(f"Extracting transaction ID from MeterValues.req: {payload.transactionId}")
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
                # Transaction not found by our assigned ID, wallbox is using its own transaction ID
                # This is a protocol deviation but some wallboxes do this
                logger.warning(f"⚠️  OCPP PROTOCOL VIOLATION: Wallbox using its own transaction ID {payload.transactionId}")
                logger.warning(f"    Expected: Wallbox should use Central System assigned transaction ID")
                logger.warning(f"    Actual: Wallbox ignoring assigned ID and using {payload.transactionId}")

                # Check if we should enforce strict OCPP compliance
                strict_compliance = SERVER_SETTINGS.get("enforce_ocpp_compliance", False)
                if strict_compliance:
                    logger.error(f"❌ REJECTING: MeterValues with non-assigned transaction ID due to strict compliance mode")
                    return MeterValuesResponse()  # Reject by not processing

                logger.info(f"🔧 ADAPTING: Processing MeterValues despite protocol violation (pragmatic mode)")
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
                logger.debug(log_message)
            
        return MeterValuesResponse()

    async def handle_unknown_action(self, charge_point_id: str, payload: dict):
        logger.warning(f"Unknown/unsupported action for {charge_point_id}: {payload}")
        return None

    async def _trigger_get_configuration(self):
        """Send GetConfiguration without waiting for response - fire and forget."""
        try:
            from app.ocpp_handler import create_ocpp_message
            import uuid

            unique_id = str(uuid.uuid4())
            request_payload = GetConfigurationRequest(key=[])
            message = create_ocpp_message(2, unique_id, request_payload, "GetConfiguration", self.charge_point_id)
            await self.handler.websocket.send(message)
            logger.debug(f"🔍 Sent GetConfiguration (fire-and-forget) for auto-detection from {self.charge_point_id}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to send GetConfiguration for auto-detection: {e}")
