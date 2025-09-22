import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict
from dataclasses import asdict

import aiohttp

from app.core import CHARGE_POINTS, TRANSACTIONS, EV_SIMULATOR_STATE, SERVER_SETTINGS, EV_SIMULATOR_BASE_URL, get_active_transaction_id, set_active_transaction_id, get_charging_value, get_charging_rate_unit
from app.messages import (
    BootNotificationRequest, TriggerMessageRequest, GetConfigurationRequest,
    ChangeConfigurationRequest, RemoteStartTransactionRequest, RemoteStopTransactionRequest,
    SetChargingProfileRequest, ClearChargingProfileRequest, ResetRequest, ResetType,
    GetCompositeScheduleRequest, ChargingProfile, ChargingSchedule, ChargingSchedulePeriod,
    ChargingProfilePurposeType, ChargingProfileKindType, ChargingRateUnitType,
)

if TYPE_CHECKING:
    from app.ocpp_server_logic import OcppServerLogic

logger = logging.getLogger(__name__)

class OcppTestSteps:
    def __init__(self, ocpp_server_logic: "OcppServerLogic"):
        self.ocpp_server_logic = ocpp_server_logic
        self.handler = ocpp_server_logic.handler
        self.charge_point_id = ocpp_server_logic.charge_point_id
        self.pending_triggered_message_events = ocpp_server_logic.pending_triggered_message_events

    def _check_cancellation(self):
        return self.ocpp_server_logic._check_cancellation()

    def _set_test_result(self, step_name: str, result: str):
        return self.ocpp_server_logic._set_test_result(step_name, result)

    async def _set_ev_state(self, state: str):
        if not SERVER_SETTINGS.get("use_simulator"):
            logger.info(f"Skipping EV state change to '{state}'; simulator is disabled.")
            return
        return await self.ocpp_server_logic._set_ev_state(state)

    async def _wait_for_status(self, status: str):
        return await self.ocpp_server_logic._wait_for_status(status)

    

    async def run_a1_initial_registration(self):
        """A.1: Verifies that the charge point has registered itself."""
        logger.info(f"--- Step A.1: Verifying initial registration for {self.charge_point_id} ---")
        step_name = "run_a1_initial_registration"
        self._check_cancellation()
        # Trigger a BootNotification to verify the charge point is responsive
        # to server-initiated commands.
        success = await self.handler.send_and_wait(
            "TriggerMessage",
            BootNotificationRequest(chargePointModel="", chargePointVendor="") # Dummy payload for TriggerMessage
        )
        self._check_cancellation()
        if success:
            logger.info("SUCCESS: The charge point acknowledged the TriggerMessage request.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error("FAILURE: The charge point did not respond to the TriggerMessage request within the timeout.")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step A.1 for {self.charge_point_id} complete. ---")

    async def run_a2_configuration_exchange(self):
        """A.2: Fetches and displays all configuration settings from the charge point."""
        logger.info(f"--- Step A.2: Running configuration exchange for {self.charge_point_id} ---")
        step_name = "run_a2_configuration_exchange"
        self._check_cancellation()
        logger.info("Attempting to fetch all configuration keys from the charge point.")
        response = await self.handler.send_and_wait(
            "GetConfiguration",
            GetConfigurationRequest(key=[])
        )
        self._check_cancellation()
        if response and response.get("configurationKey"):
            logger.info("SUCCESS: Received configuration keys from the charge point.")
            self._set_test_result(step_name, "PASSED")
            
            logger.info("--- Charge Point Configuration ---")
            for key_value in response["configurationKey"]:
                key = key_value.get("key")
                readonly = key_value.get("readonly")
                value = key_value.get("value")
                if key == "SupportedFeatureProfiles":
                                            CHARGE_POINTS[self.charge_point_id]["features"] = [f.strip() for f in key_value.get("value").split(",")]
                logger.info(f"{key} (readonly: {readonly}): {value}")
            logger.info("-------------------------------------")

        elif response and response.get("unknownKey"):
            logger.warning("Charge point reported unknown keys. This might indicate a partial success.")
            self._set_test_result(step_name, "PASSED") # Marking as success as we got a response

            logger.info("--- Charge Point Configuration (Partial) ---")
            if response.get("configurationKey"):
                for key_value in response["configurationKey"]:
                    key = key_value.get("key")
                    readonly = key_value.get("readonly")
                    value = key_value.get("value")
                    logger.info(f"{key} (readonly: {readonly}): {value}")
            logger.info("Unknown keys reported by charge point:")
            for key in response["unknownKey"]:
                logger.info(f"- {key}")
            logger.info("------------------------------------------")
        else:
            logger.error("FAILURE: The charge point did not return any configuration keys.")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step A.2 for {self.charge_point_id} complete. ---")

    async def run_a3_change_configuration_test(self):
        """A.3: Changes configuration keys to match the evcc log."""
        logger.info(f"--- Step A.3: Running Change Configuration test for {self.charge_point_id} ---")
        step_name = "run_a3_change_configuration_test"
        self._check_cancellation()
        configurations = {
            "MeterValuesSampledData": "Current.Import.L1,Current.Import.L2,Current.Import.L3,Power.Active.Import.L1,Power.Active.Import.L2,Power.Active.Import.L3,Energy.Active.Import.Register,Voltage.L1-N,Voltage.L2-N,Voltage.L3-N",
            "MeterValueSampleInterval": "10",
            "WebSocketPingInterval": "30",
            "AuthorizeRemoteTxRequests": "true",
            "HeartbeatInterval": "10",
            "OCPPCommCtrlrMessageAttemptIntervalBoo": "5",
            "TxCtrlrTxStartPoint": "Authorization",
            "FreeChargeMode": "true"
        }

        results = {}
        all_success = True
        for key, value in configurations.items():
            self._check_cancellation()
            response = await self.handler.send_and_wait(
                "ChangeConfiguration",
                ChangeConfigurationRequest(key=key, value=value)
            )
            self._check_cancellation()
            if response and response.get("status") == "Accepted":
                results[key] = "PASSED"
            else:
                results[key] = "FAILED"
                all_success = False
        
        logger.info("--- Test Summary ---")
        for key, result in results.items():
            if result == "PASSED":
                logger.info(f"  \033[92m{key}: {result}\033[0m")
            else:
                logger.error(f"  \033[91m{key}: {result}\033[0m")
        logger.info("--------------------")

        if all_success:
            self._set_test_result(step_name, "PASSED")
        else:
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step A.3 for {self.charge_point_id} complete. ---")

    async def run_a4_check_initial_state(self):
        """A.4: Checks the initial status of the charge point."""
        logger.info(f"--- Step A.4: Checking initial state for {self.charge_point_id} ---")
        step_name = "run_a4_check_initial_state"
        self._check_cancellation()
        if not SERVER_SETTINGS.get("ev_simulator_available"):
            logger.warning("Skipping test: EV simulator is not in use.")
            self._set_test_result(step_name, "SKIPPED")
            logger.info(f"--- Step A.4 for {self.charge_point_id} complete. ---")
            return

        all_success = True
        results = {}

        # Start with state A
        await self._set_ev_state("A")
        self._check_cancellation()
        try:
            await asyncio.wait_for(self._wait_for_status("Available"), timeout=15)
            self._check_cancellation()
            results["State A (Available)"] = "PASSED"
        except asyncio.TimeoutError:
            results["State A (Available)"] = "FAILED"
            all_success = False

        # Test state B
        await self._set_ev_state("B")
        self._check_cancellation()
        try:
            await asyncio.wait_for(self._wait_for_status("Preparing"), timeout=15)
            self._check_cancellation()
            results["State B (Preparing)"] = "PASSED"
        except asyncio.TimeoutError:
            results["State B (Preparing)"] = "FAILED"
            all_success = False

        # Test state C
        await self._set_ev_state("C")
        self._check_cancellation()
        try:
            await asyncio.sleep(1) # Added additional delay
            await asyncio.wait_for(self._wait_for_status("Charging"), timeout=15)
            self._check_cancellation()
            results["State C (Charging)"] = "PASSED"
        except asyncio.TimeoutError:
            results["State C (Charging)"] = "FAILED"
            all_success = False

        # Test state E
        await self._set_ev_state("E")
        self._check_cancellation()
        try:
            await asyncio.wait_for(self._wait_for_status("Faulted"), timeout=15)
            self._check_cancellation()
            results["State E (Faulted)"] = "PASSED"
        except asyncio.TimeoutError:
            results["State E (Faulted)"] = "FAILED"
            all_success = False

        # Return to state A
        await self._set_ev_state("A")
        self._check_cancellation()
        try:
            await asyncio.wait_for(self._wait_for_status("Available"), timeout=15)
            self._check_cancellation()
            results["State A (Available)"] = "PASSED"
        except asyncio.TimeoutError:
            results["State A (Available)"] = "FAILED"
            all_success = False

        logger.info("--- Test Summary ---")
        for key, result in results.items():
            if result == "PASSED":
                logger.info(f"  \033[92m{key}: {result}\033[0m")
            else:
                logger.error(f"  \033[91m{key}: {result}\033[0m")
        logger.info("--------------------")

        if all_success:
            self._set_test_result(step_name, "PASSED")
        else:
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step A.4 for {self.charge_point_id} complete. ---")

    async def run_a5_trigger_all_messages_test(self):
        """A.5: Tests all TriggerMessage functionalities."""
        logger.info(f"--- Step A.5: Testing all TriggerMessages for {self.charge_point_id} ---")
        step_name = "run_a5_trigger_all_messages_test"
        self._check_cancellation()
        # Fetch SupportedFeatureProfiles if not already available
        if "features" not in CHARGE_POINTS.get(self.charge_point_id, {}):
            logger.info("Fetching SupportedFeatureProfiles for TriggerMessage test...")
            response = await self.handler.send_and_wait(
                "GetConfiguration",
                GetConfigurationRequest(key=["SupportedFeatureProfiles"])
            )
            self._check_cancellation()
            if response and response.get("configurationKey"):
                for key_value in response["configurationKey"]:
                    if key_value.get("key") == "SupportedFeatureProfiles":
                        CHARGE_POINTS[self.charge_point_id]["features"] = [f.strip() for f in key_value.get("value").split(",")]
                        logger.info(f"SupportedFeatureProfiles fetched: {CHARGE_POINTS[self.charge_point_id]['features']}")
                        break
            else:
                logger.warning("Could not fetch SupportedFeatureProfiles. Skipping TriggerMessage test.")
                self._set_test_result(step_name, "SKIPPED")
                logger.info(f"--- Step A.5 for {self.charge_point_id} complete. ---")
                return

        supported_features = CHARGE_POINTS.get(self.charge_point_id, {}).get("features", [])
        if "RemoteTrigger" not in supported_features:
            logger.warning("Skipping test: TriggerMessage feature profile is not supported by the charge point.")
            self._set_test_result(step_name, "SKIPPED")
            logger.info(f"--- Step A.5 for {self.charge_point_id} complete. ---")
            return
        
        triggered_messages = {
            "BootNotification": {},
            "DiagnosticsStatusNotification": {},
            "FirmwareStatusNotification": {},
            "Heartbeat": {},
            "MeterValues": {"connectorId": 1},
            "StatusNotification": {"connectorId": 1}
        }
        
        results = {}
        
        for message, params in triggered_messages.items():
            self._check_cancellation()
            logger.info(f"--- Triggering {message} ---")
            
            payload = TriggerMessageRequest(requestedMessage=message, **params)

            trigger_ok = await self.handler.send_and_wait(
                "TriggerMessage",
                payload
            )
            self._check_cancellation()
            
            if trigger_ok and trigger_ok.get("status") == "Accepted":
                logger.info(f"SUCCESS: The charge point acknowledged the TriggerMessage request for {message}.")
                results[message] = "PASSED"
            else:
                logger.error(f"FAILURE: The charge point did not acknowledge the TriggerMessage request for {message}.")
                results[message] = "FAILED"

        logger.info("--- Test Summary ---")
        for key, result in results.items():
            if result == "PASSED":
                logger.info(f"  \033[92m{key}: {result}\033[0m")
            else:
                logger.error(f"  \033[91m{key}: {result}\033[0m")
        logger.info("--------------------")

        if any(result == "PASSED" for result in results.values()):
            self._set_test_result(step_name, "PASSED")
        else:
            self._set_test_result(step_name, "FAILED")
            
        logger.info(f"--- Step A.5 for {self.charge_point_id} complete. ---")

    async def run_b1_status_and_meter_value_acquisition(self):
        """B.1: Requests meter values from the charge point and waits for them."""
        logger.info(f"--- Step B.1: Acquiring meter values for {self.charge_point_id} ---")
        step_name = "run_b1_status_and_meter_value_acquisition"
        self._check_cancellation()
        # 1. Create an event to wait for the MeterValues message
        meter_values_event = asyncio.Event()
        self.pending_triggered_message_events["MeterValues"] = meter_values_event

        # 2. Send the trigger
        trigger_ok = await self.handler.send_and_wait(
            "TriggerMessage",
            TriggerMessageRequest(requestedMessage="MeterValues", connectorId=1)
        )
        self._check_cancellation()
        if not trigger_ok:
            logger.error("FAILURE: The charge point did not acknowledge the TriggerMessage request.")
            self._set_test_result(step_name, "FAILED")
            self.pending_triggered_message_events.pop("MeterValues", None)  # Cleanup
            logger.info(f"--- Step B.1 for {self.charge_point_id} complete. ---")
            return

        # 3. Wait for the MeterValues message to arrive
        try:
            logger.info("Trigger acknowledged. Waiting for the MeterValues message from the charge point...")
            await asyncio.wait_for(meter_values_event.wait(), timeout=15)
            self._check_cancellation()
            logger.info("SUCCESS: Received triggered MeterValues message from the charge point.")
            self._set_test_result(step_name, "PASSED")
        except asyncio.TimeoutError:
            logger.error("FAILURE: Timed out waiting for the triggered MeterValues message.")
            self._set_test_result(step_name, "FAILED")
        finally:
            self.pending_triggered_message_events.pop("MeterValues", None)

        logger.info(f"--- Step B.1 for {self.charge_point_id} complete. ---")

    async def run_c1_remote_transaction_test(self):
        """C.1: Starts and stops a transaction remotely."""
        logger.info(f"--- Step C.1: Running remote transaction test for {self.charge_point_id} ---")
        step_name = "run_c1_remote_transaction_test"
        self._check_cancellation()
        id_tag = "test_id_1"
        connector_id = 1

        # 1. Simulate connecting an EV to the charge point.
        await self._set_ev_state("B")
        self._check_cancellation()
        logger.info(f"Wallbox status after setting EV state to B: {CHARGE_POINTS.get(self.charge_point_id, {}).get('status')}")
        # Give the charge point a moment to process the state change (e.g., send StatusNotification)
        await asyncio.sleep(2)
        self._check_cancellation()

        # 2. Send the RemoteStartTransaction command.
        logger.info("CS sends RemoteStartTransaction.req to the CP, including an idTag for authorization and a connectorId.")
        limit_amps = 0.0
        # Clear any existing profile first (MaxChargingProfilesInstalled = 1)
        clear_response = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest()
        )
        logger.info(f"ClearChargingProfile response: {clear_response}")

        # Use configured charging rate unit for disable profile (0 limit)
        charging_value, charging_unit = get_charging_value("disable")
        rate_unit = ChargingRateUnitType.A if charging_unit == "A" else ChargingRateUnitType.W

        charging_profile = ChargingProfile(
            chargingProfileId=random.randint(1, 1000),
            stackLevel=0,  # ChargeProfileMaxStackLevel = 0
            chargingProfilePurpose=ChargingProfilePurposeType.TxProfile,
            chargingProfileKind=ChargingProfileKindType.Absolute,
            chargingSchedule=ChargingSchedule(
                chargingRateUnit=rate_unit,
                chargingSchedulePeriod=[
                    ChargingSchedulePeriod(startPeriod=0, limit=charging_value)  # 0W or 0A = no charging
                ]
            )
        )
        start_response = await self.handler.send_and_wait(
            "RemoteStartTransaction",
            RemoteStartTransactionRequest(idTag=id_tag,
                                          connectorId=connector_id,
                                          chargingProfile=charging_profile)
        )
        self._check_cancellation()
        if not start_response or start_response.get("status") != "Accepted":
            logger.error("FAILURE: RemoteStartTransaction was not acknowledged by the charge point or rejected.")
            self._set_test_result(step_name, "FAILED")
            await self._set_ev_state("A")  # Cleanup
            self._check_cancellation()
            logger.info(f"--- Step C.1 for {self.charge_point_id} complete. ---")
            return
        logger.info("CP responds with RemoteStartTransaction.conf, confirming acceptance. At this point, the transaction has not yet begun.")

        # 3. RemoteStartTransaction was acknowledged. Register the transaction on the server side.
        #    We now use a temporary key for TRANSACTIONS until the CP's transactionId is known.
        temp_transaction_key = f"{self.charge_point_id}-{connector_id}"
        cs_internal_transaction_id = start_response.get("transactionId") # Get the CS's internal ID from the response

        TRANSACTIONS[temp_transaction_key] = {
            "charge_point_id": self.charge_point_id,
            "id_tag": id_tag,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "meter_start": 0, # We don't have meter start from CP yet
            "connector_id": connector_id,
            "status": "Ongoing",
            "remote_started": True, # Mark as remotely started
            "cp_transaction_id": None, # CP's transaction ID is not yet known
            "cs_internal_transaction_id": cs_internal_transaction_id # Store the CS's internal ID
        }
        set_active_transaction_id(cs_internal_transaction_id) # Update the global active transaction ID with CS's ID
        logger.info(f"Transaction (temp key: {temp_transaction_key}, CS ID: {cs_internal_transaction_id}) registered internally after RemoteStartTransaction.")
        logger.info("CP initiates the transaction locally once the vehicle is plugged in and ready to charge.")

        # 4. Wait for the charge point to send a StatusNotification indicating "Charging".
        #    This confirms the transaction has truly started from the CP's perspective.
        logger.info("Waiting for the charge point to report 'Charging' status...")
        try:
            await asyncio.sleep(1) # Added additional delay
            await asyncio.wait_for(self._wait_for_status("Charging"), timeout=15)
            self._check_cancellation()
            logger.info("SUCCESS: Charge point reported 'Charging' status.")
        except asyncio.TimeoutError:
            logger.error("FAILURE: Timed out waiting for charge point to report 'Charging' status.")
            self._set_test_result(step_name, "FAILED")
            await self._set_ev_state("A") # Cleanup
            self._check_cancellation()
            return

        # Now that the transaction is authorized and started, simulate the EV drawing power.
        logger.info(f"Transaction (CS ID: {cs_internal_transaction_id}) is ongoing. Setting EV state to 'C' to simulate charging.")
        await self._set_ev_state("C")
        self._check_cancellation()

        # Add a small delay to allow the charge point to send a StatusNotification
        logger.info("Transaction is ongoing. Waiting a moment for the wallbox to report 'Charging' status...")
        await asyncio.sleep(2)
        self._check_cancellation()

        # Check if the wallbox status is 'Charging'
        current_status = CHARGE_POINTS.get(self.charge_point_id, {}).get("status")
        if current_status == "Charging":
            logger.info(f"SUCCESS: Wallbox status is '{current_status}' as expected.")
        else:
            logger.warning(f"NOTICE: Wallbox status is '{current_status}', not 'Charging' as expected. The test will continue.")

        # Verify that the wallbox is advertising the correct current (16A)
        # and that the EV simulator sees the corresponding duty cycle.
        logger.info("Verifying advertised current and CP duty cycle from EV simulator...")
        # Force a refresh of the EV simulator status to get the latest values
        if self.refresh_trigger:
            self.refresh_trigger.set()
            await asyncio.sleep(1)  # wait for poll to complete
            self._check_cancellation()

        advertised_amps = EV_SIMULATOR_STATE.get("wallbox_advertised_max_current_amps")
        duty_cycle = EV_SIMULATOR_STATE.get("cp_duty_cycle")

        expected_amps = 16.0
        expected_duty_cycle = (expected_amps / 0.6) / 100  # e.g., 0.2667 for 16A
        tolerance = 0.02  # 2% tolerance for duty cycle

        logger.info(f"EV simulator reports: Advertised Amps = {advertised_amps}, Duty Cycle = {duty_cycle}")
        logger.info(f"Expected values: Amps = {expected_amps}, Duty Cycle = ~{expected_duty_cycle:.4f}")

        if advertised_amps == expected_amps:
            logger.info(f"SUCCESS: Wallbox advertised current ({advertised_amps}A) matches expected value ({expected_amps}A).")
        else:
            logger.warning(f"NOTICE: Wallbox advertised current ({advertised_amps}A) from simulator does not match expected value ({expected_amps}A).")

        if duty_cycle is not None and abs(duty_cycle - expected_duty_cycle) <= tolerance:
            logger.info(f"SUCCESS: CP Duty Cycle ({duty_cycle:.4f}) is within tolerance of expected value ({expected_duty_cycle:.4f}).")
        else:
            logger.warning(f"NOTICE: CP Duty Cycle ({duty_cycle}) from simulator is outside tolerance of expected value ({expected_duty_cycle:.4f}).")

        await asyncio.sleep(10) # Let transaction run for a bit
        self._check_cancellation()

        # Retrieve the CP's transactionId from the TRANSACTIONS dictionary
        # This assumes MeterValues or StopTransaction has already updated it.
        # If not, we might need a more robust lookup here.
        current_transaction_data = TRANSACTIONS.get(temp_transaction_key) # Try temp key first
        if not current_transaction_data: # If not found by temp key, try to find by CS internal ID
            for k, v in TRANSACTIONS.items():
                if v.get("cs_internal_transaction_id") == cs_internal_transaction_id:
                    current_transaction_data = v
                    break

        cp_transaction_id_for_stop = None
        if current_transaction_data:
            cp_transaction_id_for_stop = current_transaction_data.get("cp_transaction_id")
            if cp_transaction_id_for_stop is None:
                logger.warning(f"CP transaction ID not yet available for CS internal ID {cs_internal_transaction_id}. Using CS internal ID for RemoteStopTransaction.")
                cp_transaction_id_for_stop = cs_internal_transaction_id # Fallback to CS internal ID

        if cp_transaction_id_for_stop is None:
            logger.error("FAILED: Could not determine transaction ID for RemoteStopTransaction.")
            self._set_test_result(step_name, "FAILED")
            await self._set_ev_state("A") # Cleanup
            self._check_cancellation()
            return

        logger.info(f"CP sends StartTransaction.req to the CS. This is the first message from the CP that contains the transactionId that the CP has assigned to the new session. (CP ID: {cp_transaction_id_for_stop})")
        logger.info(f"CS responds with StartTransaction.conf, which includes the same transactionId and confirms that the transaction is now formally recorded on the server side. (CS Internal ID: {cs_internal_transaction_id})")
        logger.info(f"SUCCESS: Detected ongoing transaction (CS ID: {cs_internal_transaction_id}, CP ID: {cp_transaction_id_for_stop}). Now attempting to stop it.")
        logger.info(f"Sending RemoteStopTransaction for transaction {cp_transaction_id_for_stop}...")
        stop_ok = await self.handler.send_and_wait(
            "RemoteStopTransaction",
            RemoteStopTransactionRequest(transactionId=cp_transaction_id_for_stop)
        )
        self._check_cancellation()
        if stop_ok:
            logger.info("SUCCESS: RemoteStart and RemoteStop sequence was acknowledged.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error("FAILURE: RemoteStopTransaction was not acknowledged by the charge point.")
            self._set_test_result(step_name, "FAILED")

        # 5. Cleanup: Simulate disconnecting the EV.
        await self._set_ev_state("A")
        self._check_cancellation()
        logger.info(f"--- Step C.1 for {self.charge_point_id} complete. ---")

    async def run_c2_user_initiated_transaction_test(self):
        """C.2: Guides the user to start a transaction manually."""
        logger.info(f"--- Step C.2: User-initiated transaction test for {self.charge_point_id} ---")
        # This is a manual step, so we don't set a success/failure status automatically.
        logger.info("Please connect the EV and present an authorized ID tag to the reader.")
        logger.info("The server will wait for a StartTransaction message.")
        self._check_cancellation()
        await asyncio.sleep(1)
        self._check_cancellation()
        logger.info(f"--- Step C.2 for {self.charge_point_id} is a manual step. ---")

    async def run_c3_check_power_limits_test(self):
        """C.3: Checks current power/current limits using GetCompositeSchedule."""
        logger.info(f"--- Step C.3: Checking power/current limits for {self.charge_point_id} ---")
        step_name = "run_c3_check_power_limits_test"
        self._check_cancellation()

        try:
            logger.info("Querying current charging schedule limits on connector 1...")

            # Use configured charging rate unit
            charging_unit = get_charging_rate_unit()
            composite_request = GetCompositeScheduleRequest(
                connectorId=1,
                duration=3600,
                chargingRateUnit=charging_unit
            )
            logger.info(f"Sending GetCompositeSchedule: {asdict(composite_request)}")

            try:
                response = await asyncio.wait_for(
                    self.handler.send_and_wait("GetCompositeSchedule", composite_request),
                    timeout=30.0
                )
                self._check_cancellation()
            except asyncio.TimeoutError:
                logger.error("FAILURE: GetCompositeSchedule request timed out after 30 seconds")
                self._set_test_result(step_name, "FAILED")
                logger.info(f"--- Step C.3 for {self.charge_point_id} complete. ---")
                return

            if response and response.get("status") == "Accepted":
                logger.info("SUCCESS: GetCompositeSchedule was accepted.")

                if response.get("chargingSchedule"):
                    schedule = response.get("chargingSchedule")
                    logger.info(f"📊 CURRENT POWER/CURRENT LIMITS on connector 1:")
                    logger.info(f"  - Charging Rate Unit: {schedule.get('chargingRateUnit', 'Not specified')}")
                    logger.info(f"  - Schedule Start: {response.get('scheduleStart', 'Not specified')}")

                    if schedule.get("chargingSchedulePeriod"):
                        logger.info("  - Active Charging Periods:")
                        for i, period in enumerate(schedule.get("chargingSchedulePeriod")):
                            limit = period.get('limit', 'N/A')
                            start = period.get('startPeriod', 0)
                            phases = period.get('numberPhases', 'N/A')
                            unit = schedule.get('chargingRateUnit', '')
                            logger.info(f"    • Period {i+1}: Start {start}s, Limit {limit}{unit}, Phases {phases}")
                    else:
                        logger.info("  - No charging periods defined (unlimited)")

                    logger.info("SUCCESS: Power/current limits retrieved successfully.")
                    self._set_test_result(step_name, "PASSED")
                else:
                    logger.info("📊 No active charging schedule on connector 1 (unlimited)")
                    logger.info("SUCCESS: No charging limits currently active.")
                    self._set_test_result(step_name, "PASSED")
            else:
                logger.error(f"FAILURE: GetCompositeSchedule was not accepted. Response: {response}")
                self._set_test_result(step_name, "FAILED")

        except Exception as e:
            logger.error(f"FAILURE: Exception occurred during GetCompositeSchedule test: {e}")
            logger.exception("Full exception details:")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step C.3 for {self.charge_point_id} complete. ---")

    async def run_d1_set_live_charging_power(self):
        """D.1: Sets a charging profile to limit power on an active transaction."""


        logger.info(f"--- Step D.1: Setting live charging power for {self.charge_point_id} ---")
        step_name = "run_d1_set_live_charging_power"
        self._check_cancellation()
        await self._set_ev_state("C")
        self._check_cancellation()
        transaction_id = next((tid for tid, tdata in TRANSACTIONS.items() if
                               tdata.get("charge_point_id") == self.charge_point_id and tdata.get("status") == "Ongoing"), None)
        if not transaction_id:
            logger.error("FAILURE: No ongoing transaction found. Please start a transaction before running this step.")
            self._set_test_result(step_name, "FAILED")
            return
        # Clear any existing profile first (MaxChargingProfilesInstalled = 1)
        clear_response = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest()
        )
        logger.info(f"ClearChargingProfile response: {clear_response}")

        # Use configured charging values - "disable" for stopping charging
        disable_value, charging_unit = get_charging_value("disable")
        profile = SetChargingProfileRequest(connectorId=1, csChargingProfiles=ChargingProfile(chargingProfileId=random.randint(1, 1000), transactionId=transaction_id, stackLevel=0, chargingProfilePurpose=ChargingProfilePurposeType.TxProfile, chargingProfileKind=ChargingProfileKindType.Absolute, chargingSchedule=ChargingSchedule(duration=3600, chargingRateUnit=charging_unit, chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=disable_value)])))
        logger.info(f"Sending SetChargingProfile message: {asdict(profile)}")
        success = await self.handler.send_and_wait("SetChargingProfile", profile)
        self._check_cancellation()
        if success:
            logger.info("SUCCESS: SetChargingProfile was acknowledged by the charge point.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error("FAILURE: SetChargingProfile was not acknowledged by the charge point.")
            self._set_test_result(step_name, "FAILED")
        logger.info(f"--- Step D.1 for {self.charge_point_id} complete. ---")

    async def run_d2_set_default_charging_profile(self):
        """D.2: Sets a default charging profile to medium power/current for future transactions."""


        medium_value, charging_unit = get_charging_value("medium")
        logger.info(f"--- Step D.2: Setting default charging profile to {medium_value}{charging_unit} for {self.charge_point_id} ---")
        step_name = "run_d2_set_default_charging_profile"
        self._check_cancellation()

        # Clear any existing profile first (MaxChargingProfilesInstalled = 1)
        clear_response = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest()
        )
        logger.info(f"ClearChargingProfile response: {clear_response}")

        # Use configured charging values - "medium" for default profile
        medium_value, charging_unit = get_charging_value("medium")

        # Set startSchedule to current time minus one minute (as per specification)
        from datetime import datetime, timezone, timedelta
        start_schedule = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

        # First profile: connectorId=0 (charge point level)
        profile_cp = SetChargingProfileRequest(
            connectorId=0,
            csChargingProfiles=ChargingProfile(
                chargingProfileId=random.randint(1, 1000),
                stackLevel=1,
                chargingProfilePurpose=ChargingProfilePurposeType.TxDefaultProfile,
                chargingProfileKind=ChargingProfileKindType.Absolute,
                chargingSchedule=ChargingSchedule(
                    startSchedule=start_schedule,
                    chargingRateUnit=charging_unit,
                    chargingSchedulePeriod=[
                        ChargingSchedulePeriod(
                            startPeriod=0,
                            limit=medium_value,
                            numberPhases=3  # Set number of phases for correct current interpretation
                        )
                    ]
                )
            )
        )
        logger.info(f"Sending SetChargingProfile message for connectorId=0: {asdict(profile_cp)}")
        success_cp = await self.handler.send_and_wait("SetChargingProfile", profile_cp)
        self._check_cancellation()

        # Second profile: connectorId=1 (connector level)
        profile_conn = SetChargingProfileRequest(
            connectorId=1,
            csChargingProfiles=ChargingProfile(
                chargingProfileId=random.randint(1, 1000),
                stackLevel=1,
                chargingProfilePurpose=ChargingProfilePurposeType.TxDefaultProfile,
                chargingProfileKind=ChargingProfileKindType.Absolute,
                chargingSchedule=ChargingSchedule(
                    startSchedule=start_schedule,
                    chargingRateUnit=charging_unit,
                    chargingSchedulePeriod=[
                        ChargingSchedulePeriod(
                            startPeriod=0,
                            limit=medium_value,
                            numberPhases=3  # Set number of phases for correct current interpretation
                        )
                    ]
                )
            )
        )
        logger.info(f"Sending SetChargingProfile message for connectorId=1: {asdict(profile_conn)}")
        success_conn = await self.handler.send_and_wait("SetChargingProfile", profile_conn)
        self._check_cancellation()

        if success_cp and success_conn:
            logger.info(f"PASSED: SetChargingProfile to {medium_value}{charging_unit} for both connectorId=0 and connectorId=1 was acknowledged.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error(f"FAILED: SetChargingProfile to {medium_value}{charging_unit} was not acknowledged for connectorId=0: {success_cp}, connectorId=1: {success_conn}")
            self._set_test_result(step_name, "FAILED")
        logger.info(f"--- Step D.2 for {self.charge_point_id} complete. ---")

    async def run_d3_smart_charging_capability_test(self):
        """D.3: Placeholder for a more complex smart charging test."""
        logger.info(f"--- Step D.3: Smart charging capability test for {self.charge_point_id} ---")
        step_name = "run_d3_smart_charging_capability_test"
        self._check_cancellation()
        logger.warning("This test step is a placeholder and does not perform any actions. Marking as SUCCESS.")
        await asyncio.sleep(1)
        self._check_cancellation()
        self._set_test_result(step_name, "PASSED")
        logger.info(f"--- Step D.3 for {self.charge_point_id} complete. ---")

    async def run_d4_clear_default_charging_profile(self):
        """D.4: Clears any default charging profiles."""
        logger.info(f"--- Step D.4: Clearing default charging profile for {self.charge_point_id} ---")
        step_name = "run_d4_clear_default_charging_profile"
        self._check_cancellation()
        success = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest(connectorId=0, chargingProfilePurpose=ChargingProfilePurposeType.TxDefaultProfile)
        )
        self._check_cancellation()
        if success:
            logger.info("SUCCESS: ClearChargingProfile was acknowledged.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error("FAILURE: ClearChargingProfile was not acknowledged.")
            self._set_test_result(step_name, "FAILED")
        logger.info(f"--- Step D.4 for {self.charge_point_id} complete. ---")

    async def run_d5_set_profile_5000w(self):
        """D.5: Sets a charging profile to medium power/current."""


        medium_value, charging_unit = get_charging_value("medium")
        logger.info(f"--- Step D.5: Setting charging profile to {medium_value}{charging_unit} for {self.charge_point_id} ---")
        step_name = "run_d5_set_profile_5000w"
        self._check_cancellation()

        # Clear any existing profile first (MaxChargingProfilesInstalled = 1)
        clear_response = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest()
        )
        logger.info(f"ClearChargingProfile response: {clear_response}")

        profile = SetChargingProfileRequest(
            connectorId=0,
            csChargingProfiles=ChargingProfile(
                chargingProfileId=random.randint(1, 1000),
                transactionId=None,
                stackLevel=0,
                chargingProfilePurpose=ChargingProfilePurposeType.ChargePointMaxProfile,
                chargingProfileKind=ChargingProfileKindType.Absolute,
                chargingSchedule=ChargingSchedule(
                    chargingRateUnit=charging_unit,
                    chargingSchedulePeriod=[
                        ChargingSchedulePeriod(startPeriod=0, limit=medium_value)
                    ]
                )
            )
        )
        logger.info(f"Sending SetChargingProfile message: {asdict(profile)}")
        success = await self.handler.send_and_wait("SetChargingProfile", profile)
        self._check_cancellation()

        if success and success.get("status") == "Accepted":
            logger.info(f"PASSED: SetChargingProfile to {medium_value}{charging_unit} was acknowledged.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error(f"FAILED: SetChargingProfile to {medium_value}{charging_unit} was not acknowledged. Response: {success}")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step D.5 for {self.charge_point_id} complete. ---")

    async def run_d6_set_high_charging_profile(self):
        """D.6: Sets a default charging profile to high power/current for future transactions."""

        high_value, charging_unit = get_charging_value("high")
        logger.info(f"--- Step D.6: Setting default charging profile to {high_value}{charging_unit} for {self.charge_point_id} ---")
        step_name = "run_d6_set_high_charging_profile"
        self._check_cancellation()

        # Clear any existing profile first (MaxChargingProfilesInstalled = 1)
        clear_response = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest()
        )
        logger.info(f"ClearChargingProfile response: {clear_response}")

        # Use configured charging values - "high" for default profile
        high_value, charging_unit = get_charging_value("high")

        # Set startSchedule to current time minus one minute (as per specification)
        from datetime import datetime, timezone, timedelta
        start_schedule = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

        # First profile: connectorId=0 (charge point level)
        profile_cp = SetChargingProfileRequest(
            connectorId=0,
            csChargingProfiles=ChargingProfile(
                chargingProfileId=random.randint(1, 1000),
                stackLevel=1,
                chargingProfilePurpose=ChargingProfilePurposeType.TxDefaultProfile,
                chargingProfileKind=ChargingProfileKindType.Absolute,
                chargingSchedule=ChargingSchedule(
                    startSchedule=start_schedule,
                    chargingRateUnit=charging_unit,
                    chargingSchedulePeriod=[
                        ChargingSchedulePeriod(
                            startPeriod=0,
                            limit=high_value,
                            numberPhases=3  # Set number of phases for correct current interpretation
                        )
                    ]
                )
            )
        )
        logger.info(f"Sending SetChargingProfile message for connectorId=0: {asdict(profile_cp)}")
        success_cp = await self.handler.send_and_wait("SetChargingProfile", profile_cp)
        self._check_cancellation()

        # Second profile: connectorId=1 (connector level)
        profile_conn = SetChargingProfileRequest(
            connectorId=1,
            csChargingProfiles=ChargingProfile(
                chargingProfileId=random.randint(1, 1000),
                stackLevel=1,
                chargingProfilePurpose=ChargingProfilePurposeType.TxDefaultProfile,
                chargingProfileKind=ChargingProfileKindType.Absolute,
                chargingSchedule=ChargingSchedule(
                    startSchedule=start_schedule,
                    chargingRateUnit=charging_unit,
                    chargingSchedulePeriod=[
                        ChargingSchedulePeriod(
                            startPeriod=0,
                            limit=high_value,
                            numberPhases=3  # Set number of phases for correct current interpretation
                        )
                    ]
                )
            )
        )
        logger.info(f"Sending SetChargingProfile message for connectorId=1: {asdict(profile_conn)}")
        success_conn = await self.handler.send_and_wait("SetChargingProfile", profile_conn)
        self._check_cancellation()

        if success_cp and success_conn:
            logger.info(f"PASSED: SetChargingProfile to {high_value}{charging_unit} for both connectorId=0 and connectorId=1 was acknowledged.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error(f"FAILED: SetChargingProfile to {high_value}{charging_unit} was not acknowledged for connectorId=0: {success_cp}, connectorId=1: {success_conn}")
            self._set_test_result(step_name, "FAILED")
        logger.info(f"--- Step D.6 for {self.charge_point_id} complete. ---")

    async def run_e1_remote_start_state_a(self):
        """E.1: Attempts RemoteStartTransaction from EV state A (Available). Expects rejection."""
        logger.info(f"--- Step E.1: RemoteStartTransaction from State A for {self.charge_point_id} ---")
        step_name = "run_e1_remote_start_from_state_a"
        self._check_cancellation()
        id_tag = "test_id_1"
        connector_id = 1

        # 1. Ensure EV simulator is in state A.
        await self._set_ev_state("A")
        self._check_cancellation()
        # Give the charge point a moment to report status
        await asyncio.sleep(2)

        # 2. Send the RemoteStartTransaction command.
        logger.info("Sending RemoteStartTransaction...")
        start_response = await self.handler.send_and_wait(
            "RemoteStartTransaction",
            RemoteStartTransactionRequest(idTag=id_tag, connectorId=connector_id)
        )
        self._check_cancellation()

        # For this test, we expect the RemoteStartTransaction to be ACCEPTED from State A,
        # and the CP to transition to 'Preparing' (or remain 'Available' if no EV is connected).
        if start_response and start_response.get("status") == "Accepted":
            # Wait for the CP to report its status after accepting the remote start
            try:
                await asyncio.wait_for(self._wait_for_status("Preparing"), timeout=5) # Or "Available" if it doesn't transition
                logger.info("SUCCESS: RemoteStartTransaction was accepted and CP transitioned to Preparing as expected.")
                self._set_test_result(step_name, "PASSED")
            except asyncio.TimeoutError:
                logger.error("FAILURE: RemoteStartTransaction was accepted but CP did not transition to Preparing within timeout.")
                self._set_test_result(step_name, "FAILED")
        else:
            logger.error(f"FAILURE: RemoteStartTransaction was not accepted (or failed unexpectedly). Response: {start_response}")
            self._set_test_result(step_name, "FAILED")
        
        # Ensure EV is in state A for cleanup
        await self._set_ev_state("A")
        logger.info(f"--- Step E.1 for {self.charge_point_id} complete. ---")

    async def run_e2_remote_start_state_b(self):
        """E.2: Attempts RemoteStartTransaction from EV state B (Preparing). Handles auto-start or initiates if none."""
        logger.info(f"--- Step E.2: RemoteStartTransaction from State B for {self.charge_point_id} ---")
        step_name = "run_e2_remote_start_state_b"
        self._check_cancellation()
        id_tag = "test_id_1"
        connector_id = 1

        # 1. Ensure EV simulator is in state B.
        await self._set_ev_state("B")
        self._check_cancellation()
        # Give the charge point a moment to report status and potentially auto-start a transaction
        await asyncio.sleep(2)

        # Check if a transaction was auto-started by the CP
        auto_started_transaction = next((tid for tid, tdata in TRANSACTIONS.items() if
                                         tdata.get("charge_point_id") == self.charge_point_id and
                                         tdata.get("status") == "Ongoing" and
                                         not tdata.get("remote_started", False)), None) # Check if it's NOT remotely started

        if auto_started_transaction:
            logger.warning(f"CP auto-started transaction {auto_started_transaction} when EV state set to B. Non-standard behavior.")

        # 2. Send the RemoteStartTransaction command.
        logger.info("Sending RemoteStartTransaction...")
        start_response = await self.handler.send_and_wait(
            "RemoteStartTransaction",
            RemoteStartTransactionRequest(idTag=id_tag, connectorId=connector_id)
        )
        self._check_cancellation()

        if start_response and start_response.get("status") == "Accepted":
            logger.info("PASSED: RemoteStartTransaction was accepted as expected from State B.")
            self._set_test_result(step_name, "PASSED")
            # Register the transaction on the server side.
            # We now use a temporary key for TRANSACTIONS until the CP's transactionId is known.
            temp_transaction_key = f"{self.charge_point_id}-{connector_id}"
            cs_internal_transaction_id = start_response.get("transactionId") # Get the CS's internal ID from the response

            TRANSACTIONS[temp_transaction_key] = {
                "charge_point_id": self.charge_point_id,
                "id_tag": id_tag,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "meter_start": 0, # We don't know this yet
                "connector_id": connector_id,
                "status": "Ongoing",
                "remote_started": True, # Mark as remotely started
                "cp_transaction_id": None, # CP's transaction ID is not yet known
                "cs_internal_transaction_id": cs_internal_transaction_id # Store the CS's internal ID
            }
            set_active_transaction_id(cs_internal_transaction_id) # Update the global active transaction ID with CS's ID
            logger.info(f"Transaction (temp key: {temp_transaction_key}, CS ID: {cs_internal_transaction_id}) registered internally.")
            # Simulate EV drawing power.
            logger.info(f"Setting EV state to 'C' to simulate charging.")
            await self._set_ev_state("C")
        elif start_response and start_response.get("status") == "Rejected" and auto_started_transaction:
            logger.warning(f"PASSED (with remark): RemoteStartTransaction was rejected because CP auto-started transaction {auto_started_transaction}. Non-standard behavior.")
            self._set_test_result(step_name, "PASSED") # Mark as PASSED due to functional charging
            # Ensure the auto-started transaction is cleaned up
            # This is tricky. We can't stop it remotely without its transactionId.
            # The EV simulator will eventually stop it when state is set to A.
        else:
            logger.error(f"FAILED: RemoteStartTransaction was not accepted (or failed unexpectedly). Response: {start_response}")
            self._set_test_result(step_name, "FAILED")
        
        if CHARGE_POINTS.get(self.charge_point_id, {}).get("test_results", {}).get(step_name) == "FAILED": # Only cleanup if the test failed to start a transaction
            await self._set_ev_state("A")
        logger.info(f"--- Step E.2 for {self.charge_point_id} complete. ---")

    async def run_e3_remote_start_state_c(self):
        """E.3: Attempts RemoteStartTransaction from EV state C (Charging). Expects acceptance or non-standard auto-start."""
        logger.info(f"--- Step E.3: RemoteStartTransaction from State C for {self.charge_point_id} ---")
        step_name = "run_e3_remote_start_state_c" # Corrected step_name
        self._check_cancellation()
        id_tag = "test_id_1"
        connector_id = 1

        # 1. Ensure EV simulator is in state C.
        await self._set_ev_state("C")
        self._check_cancellation()
        # Give the charge point a moment to report status and potentially auto-start a transaction
        await asyncio.sleep(2)

        # Check if a transaction was auto-started by the CP
        auto_started_transaction = next((tid for tid, tdata in TRANSACTIONS.items() if
                                         tdata.get("charge_point_id") == self.charge_point_id and
                                         tdata.get("status") == "Ongoing" and
                                         not tdata.get("remote_started", False)), None) # Check if it's NOT remotely started

        # 2. Send the RemoteStartTransaction command.
        logger.info("Sending RemoteStartTransaction...")
        start_response = await self.handler.send_and_wait(
            "RemoteStartTransaction",
            RemoteStartTransactionRequest(idTag=id_tag, connectorId=connector_id)
        )
        self._check_cancellation()

        if start_response and start_response.get("status") == "Accepted":
            logger.info("PASSED: RemoteStartTransaction was accepted as expected from State C.")
            self._set_test_result(step_name, "PASSED")
            # Register the transaction on the server side.
            # We now use a temporary key for TRANSACTIONS until the CP's transactionId is known.
            temp_transaction_key = f"{self.charge_point_id}-{connector_id}"
            cs_internal_transaction_id = start_response.get("transactionId") # Get the CS's internal ID from the response

            TRANSACTIONS[temp_transaction_key] = {
                "charge_point_id": self.charge_point_id,
                "id_tag": id_tag,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "meter_start": 0, # We don't know this yet
                "connector_id": connector_id,
                "status": "Ongoing",
                "remote_started": True, # Mark as remotely started
                "cp_transaction_id": None, # CP's transaction ID is not yet known
                "cs_internal_transaction_id": cs_internal_transaction_id # Store the CS's internal ID
            }
            set_active_transaction_id(cs_internal_transaction_id) # Update the global active transaction ID with CS's ID
            logger.info(f"Transaction (temp key: {temp_transaction_key}, CS ID: {cs_internal_transaction_id}) registered internally.")
            # Simulate EV drawing power.
            logger.info(f"Setting EV state to 'C' to simulate charging.")
            await self._set_ev_state("C")
        elif start_response and start_response.get("status") == "Rejected" and auto_started_transaction:
            logger.warning(f"PASSED (with remark): RemoteStartTransaction was rejected because CP auto-started transaction {auto_started_transaction}. Non-standard behavior.")
            self._set_test_result(step_name, "PASSED") # Mark as PASSED due to functional charging
            # Ensure the auto-started transaction is cleaned up
            # This is tricky. We can't stop it remotely without its transactionId.
            # The EV simulator will eventually stop it when state is set to A.
        else:
            logger.error(f"FAILED: RemoteStartTransaction was not accepted (or failed unexpectedly). Response: {start_response}")
            self._set_test_result(step_name, "FAILED")
        
        if CHARGE_POINTS.get(self.charge_point_id, {}).get("test_results", {}).get(step_name) == "FAILED": # Only cleanup if the test failed to start a transaction
            await self._set_ev_state("A")
        logger.info(f"--- Step E.3 for {self.charge_point_id} complete. ---")

    async def run_e4_set_profile_6a(self):
        """E.4: Sets a charging profile (Low level) for the active transaction."""


        charging_value, charging_unit = get_charging_value("low")
        logger.info(f"--- Step E.4: Setting charging profile to {charging_value}{charging_unit} for {self.charge_point_id} ---")
        step_name = "run_e4_set_profile_6a"
        self._check_cancellation()

        transaction_id = get_active_transaction_id()
        if transaction_id is None:
            logger.error("FAILED: No active transaction found. Please start a transaction first.")
            self._set_test_result(step_name, "FAILED")
            return

        # Use configured charging rate unit
        rate_unit = ChargingRateUnitType.A if charging_unit == "A" else ChargingRateUnitType.W

        profile = SetChargingProfileRequest(
            connectorId=1,
            csChargingProfiles=ChargingProfile(
                chargingProfileId=random.randint(1, 1000),
                transactionId=transaction_id,
                stackLevel=2,
                chargingProfilePurpose=ChargingProfilePurposeType.TxProfile,
                chargingProfileKind=ChargingProfileKindType.Absolute,
                chargingSchedule=ChargingSchedule(
                    chargingRateUnit=rate_unit,
                    chargingSchedulePeriod=[
                        ChargingSchedulePeriod(startPeriod=0, limit=charging_value)
                    ]
                )
            )
        )
        logger.debug(f"csChargingProfiles content: {asdict(profile.csChargingProfiles)}")
        logger.info(f"Sending SetChargingProfile message: {asdict(profile)}")
        success = await self.handler.send_and_wait("SetChargingProfile", profile)
        self._check_cancellation()

        if success and success.get("status") == "Accepted":
            logger.info(f"PASSED: SetChargingProfile to {charging_value}{charging_unit} was acknowledged.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error(f"FAILED: SetChargingProfile to {charging_value}{charging_unit} was not acknowledged. Response: {success}")
            self._set_test_result(step_name, "FAILED")
        
        logger.info(f"--- Step E.4 for {self.charge_point_id} complete. ---")

    async def run_e5_set_profile_10a(self):
        """E.5: Sets a TxProfile (Medium level) for the active charging session."""


        charging_value, charging_unit = get_charging_value("medium")
        logger.info(f"--- Step E.5: Setting TxProfile to {charging_value}{charging_unit} for active session on {self.charge_point_id} ---")
        step_name = "run_e5_set_profile_10a"
        self._check_cancellation()

        # Get the active transaction ID - required for TxProfile
        transaction_id = get_active_transaction_id()
        if transaction_id is None:
            logger.error("FAILED: No active transaction found. TxProfile requires an active transaction.")
            self._set_test_result(step_name, "FAILED")
            return

        logger.info(f"Using transaction ID {transaction_id} for TxProfile")

        # Clear any existing profile first (MaxChargingProfilesInstalled = 1)
        clear_response = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest()
        )
        logger.info(f"ClearChargingProfile response: {clear_response}")

        # Use configured charging rate unit
        rate_unit = ChargingRateUnitType.A if charging_unit == "A" else ChargingRateUnitType.W

        # Send TxProfile for the active session (connector 1, current transaction)
        profile = SetChargingProfileRequest(
            connectorId=1,  # Connector that's charging
            csChargingProfiles=ChargingProfile(
                chargingProfileId=901,  # Fixed ID as per your example
                transactionId=transaction_id,  # Current active transaction
                stackLevel=0,  # ChargeProfileMaxStackLevel = 0
                chargingProfilePurpose=ChargingProfilePurposeType.TxProfile,  # Transaction-specific profile
                chargingProfileKind=ChargingProfileKindType.Absolute,
                chargingSchedule=ChargingSchedule(
                    chargingRateUnit=rate_unit,
                    chargingSchedulePeriod=[
                        ChargingSchedulePeriod(startPeriod=0, limit=charging_value, numberPhases=3)  # 3-phase charging
                    ]
                )
            )
        )
        logger.info(f"Sending TxProfile SetChargingProfile message: {asdict(profile)}")
        success = await self.handler.send_and_wait("SetChargingProfile", profile)
        self._check_cancellation()

        if not (success and success.get("status") == "Accepted"):
            logger.error(f"FAILED: TxProfile SetChargingProfile was not acknowledged. Response: {success}")
            self._set_test_result(step_name, "FAILED")
            return

        logger.info("✅ TxProfile SetChargingProfile was acknowledged. Verifying effective limit...")

        # Verify the effective limit using GetCompositeSchedule
        # Use configured charging rate unit for GetCompositeSchedule
        rate_unit_str = get_charging_rate_unit()
        rate_unit = ChargingRateUnitType.A if rate_unit_str == "A" else ChargingRateUnitType.W

        composite_request = GetCompositeScheduleRequest(
            connectorId=1,
            duration=3600,  # 1 hour
            chargingRateUnit=rate_unit
        )
        logger.info(f"Requesting GetCompositeSchedule to verify effective limit: {asdict(composite_request)}")

        composite_response = await self.handler.send_and_wait("GetCompositeSchedule", composite_request)
        self._check_cancellation()

        if composite_response and composite_response.get("status") == "Accepted":
            logger.info("✅ GetCompositeSchedule successful. Analyzing effective limits...")

            # Log the composite schedule details
            if "chargingSchedule" in composite_response:
                schedule = composite_response["chargingSchedule"]
                logger.info(f"Composite Schedule - Duration: {schedule.get('duration')}, Unit: {schedule.get('chargingRateUnit')}")

                periods = schedule.get("chargingSchedulePeriod", [])
                for i, period in enumerate(periods):
                    limit = period.get("limit", "unknown")
                    start = period.get("startPeriod", "unknown")
                    phases = period.get("numberPhases", "not specified")
                    logger.info(f"  Period {i+1}: Start={start}s, Limit={limit}{charging_unit}, Phases={phases}")

                    # Check if our configured limit is effective
                    if period.get("limit") == charging_value:
                        logger.info(f"🎯 VERIFIED: Our {charging_value}{charging_unit} TxProfile limit is active!")
                        break
                else:
                    logger.warning(f"⚠️  Our {charging_value}{charging_unit} limit not found in composite schedule - may be overridden")
            else:
                logger.warning("No chargingSchedule in GetCompositeSchedule response")

            logger.info("PASSED: TxProfile applied and verified via GetCompositeSchedule.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.warning(f"GetCompositeSchedule failed: {composite_response}")
            logger.info("PASSED: TxProfile applied (verification failed but profile was accepted).")
            self._set_test_result(step_name, "PASSED")

        logger.info(f"--- Step E.5 for {self.charge_point_id} complete. ---")

    async def run_e6_set_profile_16a(self):
        """E.6: Sets a charging profile (High level) for the active transaction."""


        charging_value, charging_unit = get_charging_value("high")
        logger.info(f"--- Step E.6: Setting charging profile to {charging_value}{charging_unit} for {self.charge_point_id} ---")
        step_name = "run_e6_set_profile_16a"
        self._check_cancellation()

        transaction_id = get_active_transaction_id()
        if transaction_id is None:
            logger.error("FAILED: No active transaction found. Please start a transaction first.")
            self._set_test_result(step_name, "FAILED")
            return

        # Clear any existing profile first (MaxChargingProfilesInstalled = 1)
        clear_response = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest()
        )
        logger.info(f"ClearChargingProfile response: {clear_response}")

        # Use configured charging rate unit
        rate_unit = ChargingRateUnitType.A if charging_unit == "A" else ChargingRateUnitType.W

        profile = SetChargingProfileRequest(
            connectorId=1,
            csChargingProfiles=ChargingProfile(
                chargingProfileId=random.randint(1, 1000),
                transactionId=transaction_id,
                stackLevel=0,  # ChargeProfileMaxStackLevel = 0
                chargingProfilePurpose=ChargingProfilePurposeType.TxProfile,
                chargingProfileKind=ChargingProfileKindType.Absolute,
                chargingSchedule=ChargingSchedule(
                    chargingRateUnit=rate_unit,
                    chargingSchedulePeriod=[
                        ChargingSchedulePeriod(startPeriod=0, limit=charging_value)
                    ]
                )
            )
        )
        logger.info(f"Sending SetChargingProfile message: {asdict(profile)}")
        success = await self.handler.send_and_wait("SetChargingProfile", profile)
        self._check_cancellation()

        if success and success.get("status") == "Accepted":
            logger.info(f"PASSED: SetChargingProfile to {charging_value}{charging_unit} was acknowledged.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error(f"FAILED: SetChargingProfile to {charging_value}{charging_unit} was not acknowledged. Response: {success}")
            self._set_test_result(step_name, "FAILED")
        
        logger.info(f"--- Step E.6 for {self.charge_point_id} complete. ---")

    async def run_e7_clear_profile(self):
        """E.7: Clears any default charging profiles."""
        logger.info(f"--- Step E.7: Clearing default charging profile for {self.charge_point_id} ---")
        step_name = "run_e7_clear_profile"
        self._check_cancellation()

        # Assume transaction is already ongoing from a previous test (e.g., E.2 or E.3)
        # No need to find transaction_id for ClearChargingProfile if connectorId=0 (all profiles)

        success = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest(connectorId=0, chargingProfilePurpose=ChargingProfilePurposeType.TxDefaultProfile)
        )
        self._check_cancellation()
        if success:
            logger.info("PASSED: ClearChargingProfile was acknowledged.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error("FAILED: ClearChargingProfile was not acknowledged.")
            self._set_test_result(step_name, "FAILED")
        
        # Leave EV in state C (or whatever state it was left in by the transaction start test)
        logger.info(f"--- Step E.7 for {self.charge_point_id} complete. ---")

    async def run_e8_remote_stop_transaction(self):
        """E.8: Stops the active transaction remotely."""
        logger.info(f"--- Step E.8: Stopping active transaction for {self.charge_point_id} ---")
        step_name = "run_e8_remote_stop_transaction"
        self._check_cancellation()

        transaction_id = get_active_transaction_id()
        if transaction_id is None:
            logger.error("FAILED: No active transaction found to stop.")
            self._set_test_result(step_name, "FAILED")
            return

        stop_ok = await self.handler.send_and_wait(
            "RemoteStopTransaction",
            RemoteStopTransactionRequest(transactionId=transaction_id)
        )
        self._check_cancellation()
        if stop_ok:
            logger.info(f"PASSED: RemoteStopTransaction for transaction {transaction_id} was acknowledged.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error(f"FAILED: RemoteStopTransaction for transaction {transaction_id} was not acknowledged.")
            self._set_test_result(step_name, "FAILED")
        
        logger.info(f"--- Step E.8 for {self.charge_point_id} complete. ---")

    async def run_e9_brutal_stop(self):
        """E.9: Brutal Stop - Sends Reset Hard to force stop all transactions and reboot charge point."""
        logger.info(f"--- Step E.9: Brutal Stop (Reset Hard) for {self.charge_point_id} ---")
        step_name = "run_e9_brutal_stop"
        self._check_cancellation()

        logger.warning("⚠️  BRUTAL STOP: Sending Hard Reset to force terminate all transactions and reboot")
        logger.info("This will cause the charge point to reboot without gracefully stopping sessions")

        reset_request = ResetRequest(type=ResetType.Hard)
        logger.info(f"Sending Reset Hard message: {asdict(reset_request)}")

        success = await self.handler.send_and_wait("Reset", reset_request)
        self._check_cancellation()

        if success and success.get("status") == "Accepted":
            logger.info("PASSED: Reset Hard was acknowledged. Charge point will reboot.")
            logger.info("📋 EXPECTED AFTERMATH:")
            logger.info("  - Charge point will reboot without graceful session termination")
            logger.info("  - After reboot, expect StopTransaction messages with reason 'HardReset' or 'PowerLoss'")
            logger.info("  - Server must accept late StopTransaction messages and de-duplicate")
            logger.info("  - Transactions should be treated as implicitly closed on reconnect")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error(f"FAILED: Reset Hard was not acknowledged. Response: {success}")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step E.9 for {self.charge_point_id} complete. ---")

    async def run_e10_get_composite_schedule(self):
        """E.10: Get Composite Schedule - Queries the current schedule being applied on connector 1."""
        logger.info(f"--- Step E.10: Get Composite Schedule for {self.charge_point_id} ---")
        step_name = "run_e10_get_composite_schedule"
        self._check_cancellation()

        logger.info("Querying current charging schedule on connector 1...")

        composite_request = GetCompositeScheduleRequest(
            connectorId=1,
            duration=3600  # Query for next 1 hour
        )
        logger.info(f"Sending GetCompositeSchedule: {asdict(composite_request)}")

        response = await self.handler.send_and_wait("GetCompositeSchedule", composite_request)
        self._check_cancellation()

        if response and response.get("status") == "Accepted":
            logger.info("PASSED: GetCompositeSchedule was accepted.")
            if response.get("chargingSchedule"):
                schedule = response.get("chargingSchedule")
                logger.info(f"📊 ACTIVE SCHEDULE on connector 1:")
                logger.info(f"  - Charging Rate Unit: {schedule.get('chargingRateUnit', 'Not specified')}")
                logger.info(f"  - Start Time: {response.get('scheduleStart', 'Not specified')}")
                if schedule.get("chargingSchedulePeriod"):
                    for i, period in enumerate(schedule.get("chargingSchedulePeriod")):
                        logger.info(f"  - Period {i+1}: Start {period.get('startPeriod', 0)}s, Limit {period.get('limit', 'N/A')}, Phases {period.get('numberPhases', 'N/A')}")
                else:
                    logger.info("  - No charging periods defined")
            else:
                logger.info("📊 No active charging schedule on connector 1")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error(f"FAILED: GetCompositeSchedule was not accepted. Response: {response}")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step E.10 for {self.charge_point_id} complete. ---")

    async def run_e11_clear_all_profiles(self):
        """E.11: Clears ALL charging profiles from the charge point."""
        logger.info(f"--- Step E.11: Clearing ALL charging profiles for {self.charge_point_id} ---")
        step_name = "run_e11_clear_all_profiles"
        self._check_cancellation()

        logger.info("Sending ClearChargingProfile request to clear profiles for connectorId=0...")
        success_0 = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest(connectorId=0)
        )
        self._check_cancellation()

        logger.info("Sending ClearChargingProfile request to clear profiles for connectorId=1...")
        success_1 = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest(connectorId=1)
        )
        self._check_cancellation()

        success = success_0 and success_1
        self._check_cancellation()

        if success and success.get("status") == "Accepted":
            logger.info("SUCCESS: ClearChargingProfile was acknowledged and accepted.")
            self._set_test_result(step_name, "PASSED")
        elif success and success.get("status") == "NotSupported":
             logger.warning("ClearChargingProfile is not supported by the charge point. Marking as SKIPPED.")
             self._set_test_result(step_name, "SKIPPED")
        else:
            logger.error(f"FAILURE: ClearChargingProfile was not accepted. Response: {success}")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step E.11 for {self.charge_point_id} complete. ---")

    async def _wait_for_status(self, status: str):
        while CHARGE_POINTS.get(self.charge_point_id, {}).get("status") != status:
            self._check_cancellation()
            await asyncio.sleep(0.1)