"""
Contains the business logic for interacting with a charge point.
This includes handler functions for each type of OCPP message
and the logic for executing on-demand test sequences via the web UI.
"""
import asyncio
import logging
import uuid
import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict

import aiohttp

from app.state import CHARGE_POINTS, TRANSACTIONS
from app.config import EV_SIMULATOR_BASE_URL
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
    TriggerMessageRequest, GetConfigurationRequest,
    ChangeConfigurationRequest,
    RemoteStartTransactionRequest, RemoteStopTransactionRequest,
    SetChargingProfileRequest, ClearChargingProfileRequest,
    ChargingProfile, ChargingSchedule, ChargingSchedulePeriod,
    ChargingProfilePurposeType, ChargingProfileKindType, ChargingRateUnitType,
)

if TYPE_CHECKING:
    from app.ocpp_handler import OCPPHandler

logger = logging.getLogger(__name__)

VALID_ID_TAGS = ["test_id_1", "test_id_2"]
CP_STATE_MAP = {
    "Available": "CP State A",
    "Preparing": "CP State B",
    "Charging": "CP State C",
    "Finishing": "CP State X",
}

# Map from OCPP 1.6 StatusNotification status to the state of our EV simulator
OCPP_STATUS_TO_EV_STATE = {
    "Available": "A",       # Disconnected
    "Preparing": "B",       # Connected, not charging
    "Charging": "C",        # Charging
    "SuspendedEV": "B",     # Connected, not charging
    "SuspendedEVSE": "B",   # Connected, not charging
    "Finishing": "B",       # Connected, not charging (transaction ended)
    "Reserved": "A",        # Disconnected
    "Unavailable": "E",     # Error/Fault
    "Faulted": "E",         # Error/Fault
}


class OcppServerLogic:
    """
    Contains the business logic for interacting with a charge point.
    This includes running test sequences and periodic tasks.
    """

    def __init__(self, ocpp_handler: "OCPPHandler", refresh_trigger: asyncio.Event = None):
        self.handler = ocpp_handler
        self.charge_point_id = ocpp_handler.charge_point_id
        self.refresh_trigger = refresh_trigger

    async def periodic_health_checks(self):
        """Periodically sends a Heartbeat trigger to check connection health."""
        while True:
            await asyncio.sleep(60)
            try:
                logger.info(f"Triggering Heartbeat for {self.charge_point_id} as part of health check.")
                await self.handler.send_and_wait(
                    "TriggerMessage",
                    TriggerMessageRequest(requestedMessage="Heartbeat")
                )
            except Exception as e:
                logger.error(f"Health check for {self.charge_point_id} failed: {e}")
                # The main connection loop will handle the disconnection.
                break

    # --- Test Step Implementations ---

    async def run_a1_initial_registration(self):
        """A.1: Verifies that the charge point has registered itself."""
        logger.info(f"--- Step A.1: Verifying initial registration for {self.charge_point_id} ---")
        # The connection itself implies a boot notification has been received.
        # We can trigger another one for good measure.
        await self.handler.send_and_wait(
            "TriggerMessage",
            TriggerMessageRequest(requestedMessage="BootNotification")
        )
        logger.info(f"--- Step A.1 for {self.charge_point_id} complete. ---")

    async def run_a2_configuration_exchange(self):
        """A.2: Fetches configuration from the charge point."""
        logger.info(f"--- Step A.2: Running configuration exchange for {self.charge_point_id} ---")
        await self.handler.send_and_wait(
            "GetConfiguration",
            GetConfigurationRequest(key=["SupportedFeatureProfiles", "HeartbeatInterval"])
        )
        logger.info(f"--- Step A.2 for {self.charge_point_id} complete. ---")

    async def run_a3_change_configuration_test(self):
        """A.3: Changes a configuration key and verifies it."""
        logger.info(f"--- Step A.3: Running Change Configuration test for {self.charge_point_id} ---")
        key_to_change = "HeartbeatInterval"
        new_value = "55"  # A slightly unusual value to confirm it was set.
        await self.handler.send_and_wait(
            "ChangeConfiguration",
            ChangeConfigurationRequest(key=key_to_change, value=new_value)
        )
        logger.info(f"--- Step A.3 for {self.charge_point_id} complete. ---")

    async def run_b1_status_and_meter_value_acquisition(self):
        """B.1: Requests status and meter values from the charge point."""
        logger.info(f"--- Step B.1: Acquiring status and meter values for {self.charge_point_id} ---")
        await self.handler.send_and_wait(
            "TriggerMessage",
            TriggerMessageRequest(requestedMessage="StatusNotification")
        )
        await self.handler.send_and_wait(
            "TriggerMessage",
            TriggerMessageRequest(requestedMessage="MeterValues")
        )
        logger.info(f"--- Step B.1 for {self.charge_point_id} complete. ---")

    async def run_c1_remote_transaction_test(self):
        """C.1: Starts and stops a transaction remotely."""
        logger.info(f"--- Step C.1: Running remote transaction test for {self.charge_point_id} ---")
        id_tag = "test_id_1"
        connector_id = 1
        logger.info("Sending RemoteStartTransaction...")
        await self.handler.send_and_wait(
            "RemoteStartTransaction",
            RemoteStartTransactionRequest(idTag=id_tag, connectorId=connector_id)
        )
        await asyncio.sleep(10)  # Let transaction run for a bit

        transaction_id = next((tid for tid, tdata in TRANSACTIONS.items() if
                               tdata.get("charge_point_id") == self.charge_point_id and tdata.get("status") == "Ongoing"), None)

        if transaction_id:
            logger.info(f"Sending RemoteStopTransaction for transaction {transaction_id}...")
            await self.handler.send_and_wait(
                "RemoteStopTransaction",
                RemoteStopTransactionRequest(transactionId=transaction_id)
            )
        else:
            logger.error("Could not find an ongoing transaction to stop.")

        logger.info(f"--- Step C.1 for {self.charge_point_id} complete. ---")

    async def run_c2_user_initiated_transaction_test(self):
        """C.2: Guides the user to start a transaction manually."""
        logger.info(f"--- Step C.2: User-initiated transaction test for {self.charge_point_id} ---")
        logger.info("Please connect the EV and present an authorized ID tag to the reader.")
        logger.info("The server will wait for a StartTransaction message.")
        await asyncio.sleep(1)
        logger.info(f"--- Step C.2 for {self.charge_point_id} is a manual step. ---")

    async def run_d1_set_live_charging_power(self):
        """D.1: Sets a charging profile to limit power on an active transaction."""
        logger.info(f"--- Step D.1: Setting live charging power for {self.charge_point_id} ---")
        transaction_id = next((tid for tid, tdata in TRANSACTIONS.items() if
                               tdata.get("charge_point_id") == self.charge_point_id and tdata.get("status") == "Ongoing"), None)
        if not transaction_id:
            logger.error("No ongoing transaction found. Please start a transaction before running this step.")
            return
        profile = SetChargingProfileRequest(connectorId=0, csChargingProfiles=ChargingProfile(chargingProfileId=int(uuid.uuid4().int & (1 << 31) - 1), transactionId=transaction_id, stackLevel=1, chargingProfilePurpose=ChargingProfilePurposeType.txProfile, chargingProfileKind=ChargingProfileKindType.recurring, chargingSchedule=ChargingSchedule(duration=3600, chargingRateUnit=ChargingRateUnitType.amps, chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=10.0)])))
        await self.handler.send_and_wait("SetChargingProfile", profile)
        logger.info(f"--- Step D.1 for {self.charge_point_id} complete. ---")

    async def run_d2_set_default_charging_profile(self):
        """D.2: Sets a default charging profile for future transactions."""
        logger.info(f"--- Step D.2: Setting default charging profile for {self.charge_point_id} ---")
        profile = SetChargingProfileRequest(connectorId=0, csChargingProfiles=ChargingProfile(chargingProfileId=int(uuid.uuid4().int & (1 << 31) - 1), stackLevel=0, chargingProfilePurpose=ChargingProfilePurposeType.chargePointMaxProfile, chargingProfileKind=ChargingProfileKindType.recurring, chargingSchedule=ChargingSchedule(duration=86400, chargingRateUnit=ChargingRateUnitType.amps, chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=16.0)])))
        await self.handler.send_and_wait("SetChargingProfile", profile)
        logger.info(f"--- Step D.2 for {self.charge_point_id} complete. ---")

    async def run_d3_smart_charging_capability_test(self):
        """D.3: Placeholder for a more complex smart charging test."""
        logger.info(f"--- Step D.3: Smart charging capability test for {self.charge_point_id} ---")
        logger.warning("This test step is a placeholder and does not perform any actions.")
        await asyncio.sleep(1)
        logger.info(f"--- Step D.3 for {self.charge_point_id} complete. ---")

    async def run_d4_clear_default_charging_profile(self):
        """D.4: Clears any default charging profiles."""
        logger.info(f"--- Step D.4: Clearing default charging profile for {self.charge_point_id} ---")
        await self.handler.send_and_wait("ClearChargingProfile", ClearChargingProfileRequest(connectorId=0, chargingProfilePurpose=ChargingProfilePurposeType.chargePointMaxProfile))
        logger.info(f"--- Step D.4 for {self.charge_point_id} complete. ---")

    # --- Handlers for requests from Charge Point ---

    async def handle_boot_notification(self, charge_point_id: str, payload: BootNotificationRequest) -> BootNotificationResponse:
        logger.info(f"Received BootNotification from {charge_point_id}: {payload}")
        if charge_point_id not in CHARGE_POINTS:
            CHARGE_POINTS[charge_point_id] = {}
        CHARGE_POINTS[charge_point_id].update({
            "model": payload.chargePointModel,
            "vendor": payload.chargePointVendor,
            "status": "Available",
            "last_heartbeat": datetime.now(timezone.utc).isoformat()
        })
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
        logger.debug(f"Handling StatusNotification from {charge_point_id}: {payload.status}")
        cp_state_log_message = f" (equivalent to {CP_STATE_MAP.get(payload.status, 'Unknown')})"
        logger.info(f"Received StatusNotification from {charge_point_id}: Connector {payload.connectorId} is {payload.status}{cp_state_log_message}")
        if charge_point_id in CHARGE_POINTS:
            CHARGE_POINTS[charge_point_id]["status"] = payload.status

        # Sync the EV simulator's state to reflect the charge point's state.
        target_ev_state = OCPP_STATUS_TO_EV_STATE.get(payload.status)
        if target_ev_state:
            logger.debug(f"Mapped CP status '{payload.status}' to EV state '{target_ev_state}'. Attempting to sync.")
            try:
                set_url = f"{EV_SIMULATOR_BASE_URL}/api/set_state"
                async with aiohttp.ClientSession() as session:
                    logger.info(f"Syncing EV simulator state to '{target_ev_state}' based on CP status '{payload.status}'.")
                    async with session.post(set_url, json={"state": target_ev_state}, timeout=5) as resp:
                        if resp.status != 200:
                            logger.error(f"Failed to sync EV simulator state. Simulator returned {resp.status}.")
                        else:
                            logger.debug("Successfully sent state change to simulator. Waiting briefly.")
                            await asyncio.sleep(0.2) # Give simulator a moment to update its internal state
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Error while trying to sync EV simulator state: {e}")

        if self.refresh_trigger:
            logger.debug("Setting EV refresh trigger.")
            self.refresh_trigger.set()
        return StatusNotificationResponse()

    async def handle_firmware_status_notification(self, charge_point_id: str, payload: FirmwareStatusNotificationRequest) -> FirmwareStatusNotificationResponse:
        logger.info(f"Received FirmwareStatusNotification from {charge_point_id}: {payload.status}")
        return FirmwareStatusNotificationResponse()

    async def handle_diagnostics_status_notification(self, charge_point_id: str, payload: DiagnosticsStatusNotificationRequest) -> DiagnosticsStatusNotificationResponse:
        logger.info(f"Received DiagnosticsStatusNotification from {charge_point_id}: {payload.status}")
        return DiagnosticsStatusNotificationResponse()

    async def handle_heartbeat(self, charge_point_id: str, payload: HeartbeatRequest) -> HeartbeatResponse:
        logger.info(f"Received Heartbeat from {charge_point_id}")
        if charge_point_id in CHARGE_POINTS:
            CHARGE_POINTS[charge_point_id]["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
        return HeartbeatResponse(currentTime=datetime.now(timezone.utc).isoformat())

    async def handle_start_transaction(self, charge_point_id: str, payload: StartTransactionRequest) -> StartTransactionResponse:
        logger.info(f"Received StartTransaction from {charge_point_id}: {payload}")
        # Using a simple incrementing integer for transactionId. A more robust
        # implementation would use a UUID to avoid potential conflicts.
        transaction_id = len(TRANSACTIONS) + 1
        TRANSACTIONS[transaction_id] = {
            "charge_point_id": charge_point_id,
            "id_tag": payload.idTag,
            "start_time": payload.timestamp,
            "meter_start": payload.meterStart,
            "connector_id": payload.connectorId,
            "status": "Ongoing"
        }
        return StartTransactionResponse(
            transactionId=transaction_id,
            idTagInfo=IdTagInfo(status="Accepted")
        )

    async def handle_stop_transaction(self, charge_point_id: str, payload: StopTransactionRequest) -> StopTransactionResponse:
        logger.info(f"Received StopTransaction from {charge_point_id}: {payload}")
        if payload.transactionId in TRANSACTIONS:
            TRANSACTIONS[payload.transactionId].update({
                "stop_time": payload.timestamp,
                "meter_stop": payload.meterStop,
                "status": "Completed",
                "reason": payload.reason
            })
        return StopTransactionResponse(idTagInfo=IdTagInfo(status="Accepted"))

    async def handle_meter_values(self, charge_point_id: str, payload: MeterValuesRequest) -> MeterValuesResponse:
        logger.info(f"Received MeterValues from {charge_point_id} for connector {payload.connectorId}")
        if payload.transactionId and payload.transactionId in TRANSACTIONS:
            if "meter_values" not in TRANSACTIONS[payload.transactionId]:
                TRANSACTIONS[payload.transactionId]["meter_values"] = []
            TRANSACTIONS[payload.transactionId]["meter_values"].extend(payload.meterValue)
        return MeterValuesResponse()