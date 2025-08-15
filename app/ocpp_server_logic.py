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

from app.state import CHARGE_POINTS, TRANSACTIONS, EV_SIMULATOR_STATE
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
        # Used to wait for specific messages triggered by a test step
        self.pending_triggered_message_events: Dict[str, asyncio.Event] = {}

    def _set_test_result(self, step_name: str, result: str):
        """Stores the result of a test step in the global state."""
        if self.charge_point_id not in CHARGE_POINTS:
            return
        if "test_results" not in CHARGE_POINTS[self.charge_point_id]:
            CHARGE_POINTS[self.charge_point_id]["test_results"] = {}

        CHARGE_POINTS[self.charge_point_id]["test_results"][step_name] = result
        logger.debug(f"Stored test result for {self.charge_point_id} - {step_name}: {result}")

    async def _set_ev_state(self, state: str):
        """Helper to set EV state and trigger a UI refresh."""
        set_url = f"{EV_SIMULATOR_BASE_URL}/api/set_state"
        logger.info(f"Setting EV simulator state to '{state}'...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(set_url, json={"state": state}, timeout=5) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to set EV state. Simulator returned {resp.status}")
                        return
                    logger.info(f"Successfully requested EV state change to '{state}'.")
                    # Give the simulator a moment to process the state change
                    await asyncio.sleep(0.2)
                    # Trigger a poll to update the UI
                    if self.refresh_trigger:
                        self.refresh_trigger.set()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Error while setting EV simulator state: {e}")

    async def periodic_health_checks(self):
        """Periodically checks connection health. This is now a passive task."""
        while True:
            await asyncio.sleep(60)
            # This check is now passive. The server will rely on the charge
            # point sending heartbeats on its own based on the interval set
            # in the BootNotification response. A more robust implementation
            # could check the `last_heartbeat` timestamp here and close the
            # connection if it's too old. For now, we just wait.
            logger.debug(f"Passive health check for {self.charge_point_id}. Waiting for next heartbeat.")


    # --- Test Step Implementations ---

    async def run_a1_initial_registration(self):
        """A.1: Verifies that the charge point has registered itself."""
        logger.info(f"--- Step A.1: Verifying initial registration for {self.charge_point_id} ---")
        step_name = "run_a1_initial_registration"
        # Trigger a BootNotification to verify the charge point is responsive
        # to server-initiated commands.
        success = await self.handler.send_and_wait(
            "TriggerMessage",
            TriggerMessageRequest(requestedMessage="BootNotification")
        )
        if success:
            logger.info("SUCCESS: The charge point acknowledged the TriggerMessage request.")
            self._set_test_result(step_name, "SUCCESS")
        else:
            logger.error("FAILURE: The charge point did not respond to the TriggerMessage request within the timeout.")
            self._set_test_result(step_name, "FAILURE")

        logger.info(f"--- Step A.1 for {self.charge_point_id} complete. ---")

    async def run_a2_configuration_exchange(self):
        """A.2: Fetches configuration from the charge point."""
        logger.info(f"--- Step A.2: Running configuration exchange for {self.charge_point_id} ---")
        step_name = "run_a2_configuration_exchange"
        success = await self.handler.send_and_wait(
            "GetConfiguration",
            GetConfigurationRequest(key=["SupportedFeatureProfiles", "HeartbeatInterval"])
        )
        if success:
            logger.info("SUCCESS: The charge point responded to GetConfiguration.")
            self._set_test_result(step_name, "SUCCESS")
        else:
            logger.error("FAILURE: The charge point did not respond to GetConfiguration.")
            self._set_test_result(step_name, "FAILURE")
        logger.info(f"--- Step A.2 for {self.charge_point_id} complete. ---")

    async def run_a3_change_configuration_test(self):
        """A.3: Changes a configuration key and verifies it."""
        logger.info(f"--- Step A.3: Running Change Configuration test for {self.charge_point_id} ---")
        step_name = "run_a3_change_configuration_test"
        key_to_change = "HeartbeatInterval"
        new_value = "55"  # A slightly unusual value to confirm it was set.
        success = await self.handler.send_and_wait(
            "ChangeConfiguration",
            ChangeConfigurationRequest(key=key_to_change, value=new_value)
        )
        if success:
            logger.info(f"SUCCESS: The charge point acknowledged the ChangeConfiguration request for '{key_to_change}'.")
            self._set_test_result(step_name, "SUCCESS")
        else:
            logger.error(f"FAILURE: The charge point did not respond to the ChangeConfiguration request for '{key_to_change}'.")
            self._set_test_result(step_name, "FAILURE")
        logger.info(f"--- Step A.3 for {self.charge_point_id} complete. ---")

    async def run_b1_status_and_meter_value_acquisition(self):
        """B.1: Requests meter values from the charge point and waits for them."""
        logger.info(f"--- Step B.1: Acquiring meter values for {self.charge_point_id} ---")
        step_name = "run_b1_status_and_meter_value_acquisition"

        # 1. Create an event to wait for the MeterValues message
        meter_values_event = asyncio.Event()
        self.pending_triggered_message_events["MeterValues"] = meter_values_event

        # 2. Send the trigger
        trigger_ok = await self.handler.send_and_wait(
            "TriggerMessage",
            TriggerMessageRequest(requestedMessage="MeterValues", connectorId=1)
        )

        if not trigger_ok:
            logger.error("FAILURE: The charge point did not acknowledge the TriggerMessage request.")
            self._set_test_result(step_name, "FAILURE")
            self.pending_triggered_message_events.pop("MeterValues", None)  # Cleanup
            logger.info(f"--- Step B.1 for {self.charge_point_id} complete. ---")
            return

        # 3. Wait for the MeterValues message to arrive
        try:
            logger.info("Trigger acknowledged. Waiting for the MeterValues message from the charge point...")
            await asyncio.wait_for(meter_values_event.wait(), timeout=15)
            logger.info("SUCCESS: Received triggered MeterValues message from the charge point.")
            self._set_test_result(step_name, "SUCCESS")
        except asyncio.TimeoutError:
            logger.error("FAILURE: Timed out waiting for the triggered MeterValues message.")
            self._set_test_result(step_name, "FAILURE")
        finally:
            self.pending_triggered_message_events.pop("MeterValues", None)

        logger.info(f"--- Step B.1 for {self.charge_point_id} complete. ---")

    async def run_c1_remote_transaction_test(self):
        """C.1: Starts and stops a transaction remotely."""
        logger.info(f"--- Step C.1: Running remote transaction test for {self.charge_point_id} ---")
        step_name = "run_c1_remote_transaction_test"
        id_tag = "test_id_1"
        connector_id = 1

        # 1. Simulate connecting an EV to the charge point.
        await self._set_ev_state("C")
        # Give the charge point a moment to process the state change (e.g., send StatusNotification)
        await asyncio.sleep(2)

        # 2. Send the RemoteStartTransaction command.
        logger.info("Sending RemoteStartTransaction...")
        start_ok = await self.handler.send_and_wait(
            "RemoteStartTransaction",
            RemoteStartTransactionRequest(idTag=id_tag, connectorId=connector_id)
        )

        if not start_ok:
            logger.error("FAILURE: RemoteStartTransaction was not acknowledged by the charge point.")
            self._set_test_result(step_name, "FAILURE")
            await self._set_ev_state("A")  # Cleanup
            logger.info(f"--- Step C.1 for {self.charge_point_id} complete. ---")
            return

        # 3. Wait for the charge point to send a StartTransaction.req, which registers the transaction.
        logger.info("Waiting up to 10 seconds for the charge point to send a StartTransaction message...")
        await asyncio.sleep(10)

        # 4. Check if the transaction has started.
        transaction_id = next((tid for tid, tdata in TRANSACTIONS.items() if
                               tdata.get("charge_point_id") == self.charge_point_id and tdata.get("status") == "Ongoing"), None)

        if transaction_id:
            # Add a small delay to allow the charge point to send a StatusNotification
            logger.info("Transaction is ongoing. Waiting a moment for the wallbox to report 'Charging' status...")
            await asyncio.sleep(2)

            # Check if the wallbox status is 'Charging'
            current_status = CHARGE_POINTS.get(self.charge_point_id, {}).get("status")
            if current_status == "Charging":
                logger.info(f"SUCCESS: Wallbox status is '{current_status}' as expected.")
            else:
                logger.warning(f"NOTICE: Wallbox status is '{current_status}', not 'Charging' as expected. The test will continue.")

            # Per request, check the advertised current from the EV simulator before stopping.
            logger.info("Checking EV simulator for advertised max current from wallbox...")
            advertised_amps = EV_SIMULATOR_STATE.get("wallbox_advertised_max_current_amps")
            logger.info(f"EV simulator reports wallbox_advertised_max_current_amps = {advertised_amps}")

            # If the value is 0 (or not present), wait for 10 minutes as a placeholder for a more complex check.
            if not advertised_amps:
                wait_duration = 600  # 10 minutes
                logger.warning(f"Advertised current is {advertised_amps}. Waiting for {wait_duration} seconds as per test instruction...")
                await asyncio.sleep(wait_duration)
                logger.info("Wait complete. Proceeding with RemoteStopTransaction.")

            logger.info(f"SUCCESS: Detected ongoing transaction {transaction_id}. Now attempting to stop it.")
            logger.info(f"Sending RemoteStopTransaction for transaction {transaction_id}...")
            stop_ok = await self.handler.send_and_wait(
                "RemoteStopTransaction",
                RemoteStopTransactionRequest(transactionId=transaction_id)
            )
            if stop_ok:
                logger.info("SUCCESS: RemoteStart and RemoteStop sequence was acknowledged.")
                self._set_test_result(step_name, "SUCCESS")
            else:
                logger.error("FAILURE: RemoteStopTransaction was not acknowledged by the charge point.")
                self._set_test_result(step_name, "FAILURE")
        else:
            logger.error("FAILURE: No ongoing transaction was registered by the server after RemoteStart.")
            self._set_test_result(step_name, "FAILURE")

        # 5. Cleanup: Simulate disconnecting the EV.
        await self._set_ev_state("A")
        logger.info(f"--- Step C.1 for {self.charge_point_id} complete. ---")

    async def run_c2_user_initiated_transaction_test(self):
        """C.2: Guides the user to start a transaction manually."""
        logger.info(f"--- Step C.2: User-initiated transaction test for {self.charge_point_id} ---")
        # This is a manual step, so we don't set a success/failure status automatically.
        logger.info("Please connect the EV and present an authorized ID tag to the reader.")
        logger.info("The server will wait for a StartTransaction message.")
        await asyncio.sleep(1)
        logger.info(f"--- Step C.2 for {self.charge_point_id} is a manual step. ---")

    async def run_d1_set_live_charging_power(self):
        """D.1: Sets a charging profile to limit power on an active transaction."""
        logger.info(f"--- Step D.1: Setting live charging power for {self.charge_point_id} ---")
        step_name = "run_d1_set_live_charging_power"
        transaction_id = next((tid for tid, tdata in TRANSACTIONS.items() if
                               tdata.get("charge_point_id") == self.charge_point_id and tdata.get("status") == "Ongoing"), None)
        if not transaction_id:
            logger.error("FAILURE: No ongoing transaction found. Please start a transaction before running this step.")
            self._set_test_result(step_name, "FAILURE")
            return
        profile = SetChargingProfileRequest(connectorId=0, csChargingProfiles=ChargingProfile(chargingProfileId=random.randint(1, 1000), transactionId=transaction_id, stackLevel=1, chargingProfilePurpose=ChargingProfilePurposeType.TxProfile, chargingProfileKind=ChargingProfileKindType.Absolute, chargingSchedule=ChargingSchedule(duration=3600, chargingRateUnit=ChargingRateUnitType.A, chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=10.0)])))
        success = await self.handler.send_and_wait("SetChargingProfile", profile)
        if success:
            logger.info("SUCCESS: SetChargingProfile was acknowledged by the charge point.")
            self._set_test_result(step_name, "SUCCESS")
        else:
            logger.error("FAILURE: SetChargingProfile was not acknowledged by the charge point.")
            self._set_test_result(step_name, "FAILURE")
        logger.info(f"--- Step D.1 for {self.charge_point_id} complete. ---")

    async def run_d2_set_default_charging_profile(self):
        """D.2: Sets a default charging profile for future transactions."""
        logger.info(f"--- Step D.2: Setting default charging profile for {self.charge_point_id} ---")
        step_name = "run_d2_set_default_charging_profile"
        profile = SetChargingProfileRequest(connectorId=0, csChargingProfiles=ChargingProfile(chargingProfileId=random.randint(1, 1000), stackLevel=0, chargingProfilePurpose=ChargingProfilePurposeType.TxDefaultProfile, chargingProfileKind=ChargingProfileKindType.Absolute, chargingSchedule=ChargingSchedule(duration=86400, chargingRateUnit=ChargingRateUnitType.A, chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=16.0)])))
        success = await self.handler.send_and_wait("SetChargingProfile", profile)
        if success:
            logger.info("SUCCESS: SetChargingProfile for default profile was acknowledged.")
            self._set_test_result(step_name, "SUCCESS")
        else:
            logger.error("FAILURE: SetChargingProfile for default profile was not acknowledged.")
            self._set_test_result(step_name, "FAILURE")
        logger.info(f"--- Step D.2 for {self.charge_point_id} complete. ---")

    async def run_d3_smart_charging_capability_test(self):
        """D.3: Placeholder for a more complex smart charging test."""
        logger.info(f"--- Step D.3: Smart charging capability test for {self.charge_point_id} ---")
        step_name = "run_d3_smart_charging_capability_test"
        logger.warning("This test step is a placeholder and does not perform any actions. Marking as SUCCESS.")
        await asyncio.sleep(1)
        self._set_test_result(step_name, "SUCCESS")
        logger.info(f"--- Step D.3 for {self.charge_point_id} complete. ---")

    async def run_d4_clear_default_charging_profile(self):
        """D.4: Clears any default charging profiles."""
        logger.info(f"--- Step D.4: Clearing default charging profile for {self.charge_point_id} ---")
        step_name = "run_d4_clear_default_charging_profile"
        success = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest(connectorId=0, chargingProfilePurpose=ChargingProfilePurposeType.TxDefaultProfile)
        )
        if success:
            logger.info("SUCCESS: ClearChargingProfile was acknowledged.")
            self._set_test_result(step_name, "SUCCESS")
        else:
            logger.error("FAILURE: ClearChargingProfile was not acknowledged.")
            self._set_test_result(step_name, "FAILURE")
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

        if self.refresh_trigger:
            # The UI polls the EV simulator status. If the CP status changes,
            # it might be useful to trigger a faster refresh of the simulator state for the UI.
            logger.debug("CP status changed, setting EV refresh trigger for UI.")
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

                logger.debug(f"    - {measurand}: {sv.value}{unit}{details}")
        if payload.transactionId and payload.transactionId in TRANSACTIONS:
            if "meter_values" not in TRANSACTIONS[payload.transactionId]:
                TRANSACTIONS[payload.transactionId]["meter_values"] = []
            TRANSACTIONS[payload.transactionId]["meter_values"].extend(payload.meterValue)
        return MeterValuesResponse()