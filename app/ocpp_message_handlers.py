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

RFID_CARDS = {
    "first_card": "Accepted",
    "second_card": "Invalid"
}
VALID_ID_TAGS = ["50600020100021"]

rfid_test_state = {
    "active": False,
    "cards_presented": [],
    "test_start_time": None
}
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
            self.pending_triggered_message_events["BootNotification"].set()

        logger.info(f"🔌 Received BootNotification from {charge_point_id}: {payload}")

        if charge_point_id not in CHARGE_POINTS:
            CHARGE_POINTS[charge_point_id] = {}
        else:
            logger.debug(f"Updating existing entry for charge point {charge_point_id}")
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

        return BootNotificationResponse(
            status="Accepted",
            currentTime=datetime.now(timezone.utc).isoformat(),
            interval=60
        )

    async def handle_authorize(self, charge_point_id: str, payload: AuthorizeRequest) -> AuthorizeResponse:
        logger.info(f"📡 OCPP: Authorize request from {charge_point_id} for idTag: {payload.idTag}")

        if rfid_test_state["active"]:
            card_count = len(rfid_test_state["cards_presented"])

            if payload.idTag not in rfid_test_state["cards_presented"]:
                rfid_test_state["cards_presented"].append(payload.idTag)
                card_count = len(rfid_test_state["cards_presented"])

                if card_count == 1:
                    status = "Accepted"
                    logger.info(f"    🎫 RFID Test - Card #{card_count} (FIRST): {payload.idTag} → Status: {status}")
                    logger.info("    💡 TIP: Present a DIFFERENT card for the second test (wallbox may not re-read same card)")
                else:
                    status = "Invalid"
                    logger.info(f"    🎫 RFID Test - Card #{card_count} (SUBSEQUENT): {payload.idTag} → Status: {status}")
            else:
                card_index = rfid_test_state["cards_presented"].index(payload.idTag) + 1
                status = "Accepted" if card_index == 1 else "Invalid"
                logger.info(f"    🎫 RFID Test - Repeat Card #{card_index}: {payload.idTag} → Status: {status}")

        elif payload.idTag in RFID_CARDS:
            status = RFID_CARDS[payload.idTag]
            logger.info(f"    🎫 RFID Card: {payload.idTag} → Status: {status}")
        elif payload.idTag in VALID_ID_TAGS:
            status = "Accepted"
            logger.info(f"    ✅ Legacy ID Tag: {payload.idTag} → Status: {status}")
        else:
            status = "Invalid"
            logger.info(f"    ❌ Unknown ID Tag: {payload.idTag} → Status: {status}")

        logger.info(f"    ✅ Authorization {status} for idTag: {payload.idTag}")

        if status == "Accepted":
            if charge_point_id in CHARGE_POINTS:
                CHARGE_POINTS[charge_point_id]["accepted_rfid"] = payload.idTag
                logger.debug(f"    📝 Stored accepted RFID '{payload.idTag}' in charge point data")

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

            if payload.timestamp and "first_status_time" not in CHARGE_POINTS[charge_point_id]:
                CHARGE_POINTS[charge_point_id]["first_status_time"] = payload.timestamp
                logger.info(f"📅 Captured first StatusNotification timestamp from {charge_point_id}: {payload.timestamp}")

        is_first_status = self.initial_status_received and not self.initial_status_received.is_set()
        if (is_first_status and
            not SERVER_SETTINGS.get("auto_detection_completed", False) and
            "auto_detection_triggered" not in CHARGE_POINTS[charge_point_id]):
            logger.info("🔍 Triggering GetConfiguration for auto-detection (fire-and-forget) on FIRST StatusNotification...")
            CHARGE_POINTS[charge_point_id]["auto_detection_triggered"] = True
            asyncio.create_task(self._trigger_get_configuration())

        if self.initial_status_received and not self.initial_status_received.is_set():
            self.initial_status_received.set()

        if self.ocpp_server_logic.refresh_trigger and SERVER_SETTINGS.get("ev_simulator_available"):
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

        # Generate a transaction ID based on timestamp
        import time
        transaction_id = int(time.time() * 1000) % 100000  # Use last 5 digits of timestamp

        existing_transaction_data = None
        existing_transaction_key = None
        for key, t_data in TRANSACTIONS.items():
            if t_data.get("charge_point_id") == charge_point_id and \
               t_data.get("connector_id") == payload.connectorId and \
               t_data.get("remote_started") is True and \
               t_data.get("status") == "Ongoing":
                existing_transaction_data = t_data
                existing_transaction_key = key
                TRANSACTIONS[transaction_id] = TRANSACTIONS.pop(key)
                break

        if existing_transaction_data:
            # Preserve the remote_started flag and id_tag from the placeholder
            preserved_id_tag = existing_transaction_data.get("id_tag")
            existing_transaction_data.update({
                "start_time": payload.timestamp,
                "meter_start": payload.meterStart,
                "remote_started": True,  # KEEP True - this was a remote start!
                "transaction_id": transaction_id,
                "cp_transaction_id": transaction_id,
            })
            # Keep id_tag if it was set (not anonymous)
            if preserved_id_tag:
                existing_transaction_data["id_tag"] = preserved_id_tag
                existing_transaction_data.pop("anonymous", None)
            else:
                existing_transaction_data["anonymous"] = True
                existing_transaction_data.pop("id_tag", None)

            logger.info(f"✅ OCPP: Confirmed remote transaction (CS assigned ID: {transaction_id}) with StartTransaction data.")
            logger.debug(f"   🔄 Updated transaction from placeholder key '{existing_transaction_key}' to real ID {transaction_id}")
            transaction_id_to_return = transaction_id
        else:
            TRANSACTIONS[transaction_id] = {
                "charge_point_id": charge_point_id,
                # "id_tag": payload.idTag,  # Removed - no RFID storage for anonymous transactions
                "start_time": "0000-00-00T00:00:00.000Z",
                "meter_start": payload.meterStart,
                "connector_id": payload.connectorId,
                "status": "Ongoing",
                "remote_started": False,
                "transaction_id": transaction_id,
                "anonymous": True  # Flag to indicate no idTag stored
            }
            logger.info(f"💫 OCPP: Created new transaction (ID: {transaction_id}) initiated by CP.")
            transaction_id_to_return = transaction_id

        set_active_transaction_id(transaction_id)
        return StartTransactionResponse(
            transactionId=transaction_id_to_return,
            idTagInfo=IdTagInfo(status="Accepted")
        )

    async def handle_stop_transaction(self, charge_point_id: str, payload: StopTransactionRequest) -> StopTransactionResponse:
        logger.info(f"Received StopTransaction from {charge_point_id}: {payload}")

        transaction_data = None
        transaction_key = None

        if payload.transactionId:
            transaction_data = TRANSACTIONS.get(payload.transactionId)
            transaction_key = payload.transactionId
            if transaction_data:
                logger.debug(f"Found transaction {payload.transactionId} by its CP ID for StopTransaction.")

        if not transaction_data:
            if not payload.transactionId:
                logger.info(f"StopTransaction received with empty transaction ID. Requesting status and meter values from {charge_point_id}...")
                try:
                    from app.messages import TriggerMessageRequest, MessageTrigger

                    # First trigger StatusNotification
                    status_response = await self.ocpp_server_logic.handler.send_and_wait(
                        "TriggerMessage",
                        TriggerMessageRequest(requestedMessage=MessageTrigger.StatusNotification, connectorId=1),
                        timeout=10
                    )
                    logger.debug(f"TriggerMessage for StatusNotification response: {status_response}")

                    meter_response = await self.ocpp_server_logic.handler.send_and_wait(
                        "TriggerMessage",
                        TriggerMessageRequest(requestedMessage=MessageTrigger.MeterValues, connectorId=1),
                        timeout=10
                    )
                    logger.debug(f"TriggerMessage for MeterValues response: {meter_response}")

                    await asyncio.sleep(2)
                except Exception as e:
                    logger.warning(f"Failed to trigger status/meter updates: {e}")

            for tid, tdata in TRANSACTIONS.items():
                if tdata.get("charge_point_id") == charge_point_id and tdata.get("status") == "Ongoing":
                    transaction_data = tdata
                    transaction_key = tid
                    logger.debug(f"Found ongoing transaction {tid} for charge point {charge_point_id} for StopTransaction.")
                    break

        if transaction_data and transaction_key:
            transaction_data.update({
                "stop_time": payload.timestamp,
                "meter_stop": payload.meterStop,
                "status": "Completed",
                "reason": payload.reason
            })
            if transaction_data.get("cp_transaction_id") is None:
                transaction_data["cp_transaction_id"] = payload.transactionId

            del TRANSACTIONS[transaction_key]
            logger.info(f"Transaction {transaction_key} removed from active transactions.")

            set_active_transaction_id(None)
            await asyncio.sleep(0.1)
            return StopTransactionResponse()
        else:
            if not payload.transactionId:
                logger.info(f"StopTransaction received with empty transaction ID from {charge_point_id}. No active transaction found. Acknowledging stop.")
            else:
                logger.info(f"StopTransaction received for transaction (CP ID: {payload.transactionId}) not found in active records. Acknowledging stop.")
            set_active_transaction_id(None)
            await asyncio.sleep(0.1)
            return StopTransactionResponse()

    async def handle_meter_values(self, charge_point_id: str, payload: MeterValuesRequest) -> MeterValuesResponse:
        if "MeterValues" in self.pending_triggered_message_events:
            is_triggered = any(
                sv.context == "Trigger" for mv in payload.meterValue for sv in mv.sampledValue
            )
            if is_triggered:
                logger.debug("Detected a triggered MeterValues message, setting event.")
                self.pending_triggered_message_events["MeterValues"].set()

        logger.debug(f"Received MeterValues from {charge_point_id} for connector {payload.connectorId}")

        if payload.transactionId is not None:
            logger.debug(f"Extracting transaction ID from MeterValues.req: {payload.transactionId}")
            transaction_data = TRANSACTIONS.get(payload.transactionId)

            if transaction_data:
                logger.debug(f"Found transaction {payload.transactionId} by its CP ID.")

                if transaction_data.get("cp_transaction_id") is None:
                    transaction_data["cp_transaction_id"] = payload.transactionId

                if "meter_values" not in transaction_data:
                    transaction_data["meter_values"] = []
                transaction_data["meter_values"].extend(payload.meterValue)
                set_active_transaction_id(payload.transactionId)

            else:
                logger.warning(f"⚠️  OCPP PROTOCOL VIOLATION: Wallbox using its own transaction ID {payload.transactionId}")
                logger.warning(f"    Expected: Wallbox should use Central System assigned transaction ID")
                logger.warning(f"    Actual: Wallbox ignoring assigned ID and using {payload.transactionId}")

                strict_compliance = SERVER_SETTINGS.get("enforce_ocpp_compliance", False)
                if strict_compliance:
                    logger.error(f"❌ REJECTING: MeterValues with non-assigned transaction ID due to strict compliance mode")
                    return MeterValuesResponse()

                logger.info(f"🔧 ADAPTING: Processing MeterValues despite protocol violation (pragmatic mode)")
                TRANSACTIONS[payload.transactionId] = {
                    "charge_point_id": charge_point_id,
                    "id_tag": "unknown",
                    "start_time": payload.meterValue[0].timestamp if payload.meterValue else datetime.now(timezone.utc).isoformat(),
                    "meter_start": payload.meterValue[0].sampledValue[0].value if payload.meterValue and payload.meterValue[0].sampledValue else 0,
                    "connector_id": payload.connectorId,
                    "status": "Ongoing",
                    "remote_started": False,
                    "cp_transaction_id": payload.transactionId,
                    "cs_internal_transaction_id": None
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

                logger.debug(f"    - {measurand}: {sv.value}{unit}{details}")

        return MeterValuesResponse()

    async def handle_unknown_action(self, charge_point_id: str, payload: dict):
        logger.warning(f"Unknown/unsupported action for {charge_point_id}: {payload}")
        return None

    async def _trigger_get_configuration(self):
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
