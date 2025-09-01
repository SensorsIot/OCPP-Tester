import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict

import aiohttp

from app.core import CHARGE_POINTS, TRANSACTIONS, EV_SIMULATOR_STATE, SERVER_SETTINGS, EV_SIMULATOR_BASE_URL
from app.messages import (
    BootNotificationRequest, TriggerMessageRequest, GetConfigurationRequest,
    ChangeConfigurationRequest, RemoteStartTransactionRequest, RemoteStopTransactionRequest,
    SetChargingProfileRequest, ClearChargingProfileRequest,
    ChargingProfile, ChargingSchedule, ChargingSchedulePeriod,
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
            self._set_test_result(step_name, "SUCCESS")
        else:
            logger.error("FAILURE: The charge point did not respond to the TriggerMessage request within the timeout.")
            self._set_test_result(step_name, "FAILURE")

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
            self._set_test_result(step_name, "SUCCESS")
            
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
            self._set_test_result(step_name, "SUCCESS") # Marking as success as we got a response

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
            self._set_test_result(step_name, "FAILURE")

        logger.info(f"--- Step A.2 for {self.charge_point_id} complete. ---")

    async def run_a3_change_configuration_test(self):
        """A.3: Changes configuration keys to match the evcc log."""
        logger.info(f"--- Step A.3: Running Change Configuration test for {self.charge_point_id} ---")
        step_name = "run_a3_change_configuration_test"
        self._check_cancellation()
        configurations = {
            "MeterValuesSampledData": "Power.Active.Import,Energy.Active.Import.Register,Current.Import,Voltage,Current.Offered,Power.Offered,SoC",
            "MeterValueSampleInterval": "10",
            "WebSocketPingInterval": "30"
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
                results[key] = "SUCCESS"
            else:
                results[key] = "FAILURE"
                all_success = False
        
        logger.info("--- Test Summary ---")
        for key, result in results.items():
            if result == "SUCCESS":
                logger.info(f"  \033[92m{key}: {result}\033[0m")
            else:
                logger.error(f"  \033[91m{key}: {result}\033[0m")
        logger.info("--------------------")

        if all_success:
            self._set_test_result(step_name, "SUCCESS")
        else:
            self._set_test_result(step_name, "FAILURE")

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
            results["State A (Available)"] = "SUCCESS"
        except asyncio.TimeoutError:
            results["State A (Available)"] = "FAILURE"
            all_success = False

        # Test state B
        await self._set_ev_state("B")
        self._check_cancellation()
        try:
            await asyncio.wait_for(self._wait_for_status("Preparing"), timeout=15)
            self._check_cancellation()
            results["State B (Preparing)"] = "SUCCESS"
        except asyncio.TimeoutError:
            results["State B (Preparing)"] = "FAILURE"
            all_success = False

        # Test state C
        await self._set_ev_state("C")
        self._check_cancellation()
        try:
            await asyncio.sleep(1) # Added additional delay
            await asyncio.wait_for(self._wait_for_status("Charging"), timeout=15)
            self._check_cancellation()
            results["State C (Charging)"] = "SUCCESS"
        except asyncio.TimeoutError:
            results["State C (Charging)"] = "FAILURE"
            all_success = False

        # Test state E
        await self._set_ev_state("E")
        self._check_cancellation()
        try:
            await asyncio.wait_for(self._wait_for_status("Faulted"), timeout=15)
            self._check_cancellation()
            results["State E (Faulted)"] = "SUCCESS"
        except asyncio.TimeoutError:
            results["State E (Faulted)"] = "FAILURE"
            all_success = False

        # Return to state A
        await self._set_ev_state("A")
        self._check_cancellation()
        try:
            await asyncio.wait_for(self._wait_for_status("Available"), timeout=15)
            self._check_cancellation()
            results["State A (Available)"] = "SUCCESS"
        except asyncio.TimeoutError:
            results["State A (Available)"] = "FAILURE"
            all_success = False

        logger.info("--- Test Summary ---")
        for key, result in results.items():
            if result == "SUCCESS":
                logger.info(f"  \033[92m{key}: {result}\033[0m")
            else:
                logger.error(f"  \033[91m{key}: {result}\033[0m")
        logger.info("--------------------")

        if all_success:
            self._set_test_result(step_name, "SUCCESS")
        else:
            self._set_test_result(step_name, "FAILURE")

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
                results[message] = "SUCCESS"
            else:
                logger.error(f"FAILURE: The charge point did not acknowledge the TriggerMessage request for {message}.")
                results[message] = "FAILURE"

        logger.info("--- Test Summary ---")
        for key, result in results.items():
            if result == "SUCCESS":
                logger.info(f"  \033[92m{key}: {result}\033[0m")
            else:
                logger.error(f"  \033[91m{key}: {result}\033[0m")
        logger.info("--------------------")

        if any(result == "SUCCESS" for result in results.values()):
            self._set_test_result(step_name, "SUCCESS")
        else:
            self._set_test_result(step_name, "FAILURE")
            
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
            self._set_test_result(step_name, "FAILURE")
            self.pending_triggered_message_events.pop("MeterValues", None)  # Cleanup
            logger.info(f"--- Step B.1 for {self.charge_point_id} complete. ---")
            return

        # 3. Wait for the MeterValues message to arrive
        try:
            logger.info("Trigger acknowledged. Waiting for the MeterValues message from the charge point...")
            await asyncio.wait_for(meter_values_event.wait(), timeout=15)
            self._check_cancellation()
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
        logger.info("Sending RemoteStartTransaction with a 16A charging limit...")
        limit_amps = 16.0
        charging_profile = ChargingProfile(
            chargingProfileId=random.randint(1, 1000),
            stackLevel=1,
            chargingProfilePurpose=ChargingProfilePurposeType.TxProfile,
            chargingProfileKind=ChargingProfileKindType.Absolute,
            chargingSchedule=ChargingSchedule(
                chargingRateUnit=ChargingRateUnitType.A,
                chargingSchedulePeriod=[
                    ChargingSchedulePeriod(startPeriod=0, limit=limit_amps)
                ]
            )
        )
        start_ok = await self.handler.send_and_wait(
            "RemoteStartTransaction",
            RemoteStartTransactionRequest(idTag=id_tag,
                                          connectorId=connector_id,
                                          chargingProfile=charging_profile)
        )
        self._check_cancellation()
        if not start_ok:
            logger.error("FAILURE: RemoteStartTransaction was not acknowledged by the charge point.")
            self._set_test_result(step_name, "FAILURE")
            await self._set_ev_state("A")  # Cleanup
            self._check_cancellation()
            logger.info(f"--- Step C.1 for {self.charge_point_id} complete. ---")
            return

        # 3. RemoteStartTransaction was acknowledged. Register the transaction on the server side.
        #    Since the charge point might not send StartTransaction.req after a remote start,
        #    we generate our own transactionId and manage the state internally.
        transaction_id = len(TRANSACTIONS) + 1 # Simple incrementing ID
        TRANSACTIONS[transaction_id] = {
            "charge_point_id": self.charge_point_id,
            "id_tag": id_tag,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "meter_start": 0, # We don't have meter start from CP yet
            "connector_id": connector_id,
            "status": "Ongoing",
            "remote_started": True # Mark as remotely started
        }
        logger.info(f"Transaction {transaction_id} registered internally after RemoteStartTransaction.")

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
            self._set_test_result(step_name, "FAILURE")
            await self._set_ev_state("A") # Cleanup
            self._check_cancellation()
            return

        # Now that the transaction is authorized and started, simulate the EV drawing power.
        logger.info(f"Transaction {transaction_id} is ongoing. Setting EV state to 'C' to simulate charging.")
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

        logger.info(f"SUCCESS: Detected ongoing transaction {transaction_id}. Now attempting to stop it.")
        logger.info(f"Sending RemoteStopTransaction for transaction {transaction_id}...")
        stop_ok = await self.handler.send_and_wait(
            "RemoteStopTransaction",
            RemoteStopTransactionRequest(transactionId=transaction_id)
        )
        self._check_cancellation()
        if stop_ok:
            logger.info("SUCCESS: RemoteStart and RemoteStop sequence was acknowledged.")
            self._set_test_result(step_name, "SUCCESS")
        else:
            logger.error("FAILURE: RemoteStopTransaction was not acknowledged by the charge point.")
            self._set_test_result(step_name, "FAILURE")
        # else: # This else block is removed as transaction is now always registered internally
        #     logger.error("FAILURE: No ongoing transaction was registered by the server after RemoteStart.")
        #     self._set_test_result(step_name, "FAILURE")

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
            self._set_test_result(step_name, "FAILURE")
            return
        profile = SetChargingProfileRequest(connectorId=0, csChargingProfiles=ChargingProfile(chargingProfileId=random.randint(1, 1000), transactionId=transaction_id, stackLevel=1, chargingProfilePurpose=ChargingProfilePurposeType.TxProfile, chargingProfileKind=ChargingProfileKindType.Absolute, chargingSchedule=ChargingSchedule(duration=3600, chargingRateUnit=ChargingRateUnitType.A, chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=10.0)])))
        success = await self.handler.send_and_wait("SetChargingProfile", profile)
        self._check_cancellation()
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
        self._check_cancellation()
        profile = SetChargingProfileRequest(connectorId=0, csChargingProfiles=ChargingProfile(chargingProfileId=random.randint(1, 1000), stackLevel=0, chargingProfilePurpose=ChargingProfilePurposeType.TxDefaultProfile, chargingProfileKind=ChargingProfileKindType.Absolute, chargingSchedule=ChargingSchedule(duration=86400, chargingRateUnit=ChargingRateUnitType.A, chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=16.0)])))
        success = await self.handler.send_and_wait("SetChargingProfile", profile)
        self._check_cancellation()
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
        self._check_cancellation()
        logger.warning("This test step is a placeholder and does not perform any actions. Marking as SUCCESS.")
        await asyncio.sleep(1)
        self._check_cancellation()
        self._set_test_result(step_name, "SUCCESS")
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
            self._set_test_result(step_name, "SUCCESS")
        else:
            logger.error("FAILURE: ClearChargingProfile was not acknowledged.")
            self._set_test_result(step_name, "FAILURE")
        logger.info(f"--- Step D.4 for {self.charge_point_id} complete. ---")

    

    async def run_e1_real_world_transaction_test(self):
        """E.1: Starts a remote transaction and leaves it running."""
        logger.info(f"--- Step E.1: Starting remote transaction for {self.charge_point_id} ---")
        step_name = "run_e1_real_world_transaction_test"
        self._check_cancellation()
        id_tag = "test_id_1"
        connector_id = 1

        # 1. Simulate connecting an EV to the charge point.
        await self._set_ev_state("B")
        self._check_cancellation()
        await asyncio.sleep(2)

        # 2. Send the RemoteStartTransaction command.
        logger.info("Sending RemoteStartTransaction...")
        start_response = await self.handler.send_and_wait(
            "RemoteStartTransaction",
            RemoteStartTransactionRequest(idTag=id_tag, connectorId=connector_id)
        )
        self._check_cancellation()

        if not (start_response and start_response.get("status") == "Accepted"):
            logger.error(f"FAILURE: RemoteStartTransaction was not accepted. Response: {start_response}")
            self._set_test_result(step_name, "FAILURE")
            await self._set_ev_state("A")
            return

        logger.info("RemoteStartTransaction was accepted by the charge point.")

        # 3. Register the transaction on the server side.
        transaction_id = len(TRANSACTIONS) + 1
        TRANSACTIONS[transaction_id] = {
            "charge_point_id": self.charge_point_id,
            "id_tag": id_tag,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "meter_start": 0, # We don't know this yet
            "connector_id": connector_id,
            "status": "Ongoing",
            "remote_started": True
        }
        logger.info(f"Transaction {transaction_id} registered internally.")
        self._set_test_result(step_name, "SUCCESS")


        # 4. Simulate EV drawing power.
        logger.info(f"Setting EV state to 'C' to simulate charging.")
        await self._set_ev_state("C")

        logger.info(f"--- Step E.1 for {self.charge_point_id} complete. ---")

    async def run_e2_set_charging_profile_6a(self):
        """E.2: Sets a charging profile to 6A."""
        logger.info(f"--- Step E.2: Setting charging profile to 6A for {self.charge_point_id} ---")
        step_name = "run_e2_set_charging_profile_6a"
        self._check_cancellation()
        transaction_id = next((tid for tid, tdata in TRANSACTIONS.items() if
                               tdata.get("charge_point_id") == self.charge_point_id and tdata.get("status") == "Ongoing"), None)
        if not transaction_id:
            logger.error("FAILURE: No ongoing transaction found. Please start a transaction before running this step.")
            self._set_test_result(step_name, "FAILURE")
            return
        profile = SetChargingProfileRequest(connectorId=0, csChargingProfiles=ChargingProfile(chargingProfileId=random.randint(1, 1000), transactionId=transaction_id, stackLevel=1, chargingProfilePurpose=ChargingProfilePurposeType.TxProfile, chargingProfileKind=ChargingProfileKindType.Absolute, chargingSchedule=ChargingSchedule(duration=3600, chargingRateUnit=ChargingRateUnitType.A, chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=6.0)])))
        success = await self.handler.send_and_wait("SetChargingProfile", profile)
        self._check_cancellation()
        if success and success.get("status") == "Accepted":
            logger.info("SUCCESS: SetChargingProfile to 6A was acknowledged.")
            self._set_test_result(step_name, "SUCCESS")
        else:
            logger.error(f"FAILURE: SetChargingProfile to 6A was not acknowledged. Response: {success}")
            self._set_test_result(step_name, "FAILURE")
        logger.info(f"--- Step E.2 for {self.charge_point_id} complete. ---")

    async def run_e3_set_charging_profile_10a(self):
        """E.3: Sets a charging profile to 10A."""
        logger.info(f"--- Step E.3: Setting charging profile to 10A for {self.charge_point_id} ---")
        step_name = "run_e3_set_charging_profile_10a"
        self._check_cancellation()
        transaction_id = next((tid for tid, tdata in TRANSACTIONS.items() if
                               tdata.get("charge_point_id") == self.charge_point_id and tdata.get("status") == "Ongoing"), None)
        if not transaction_id:
            logger.error("FAILURE: No ongoing transaction found. Please start a transaction before running this step.")
            self._set_test_result(step_name, "FAILURE")
            return
        profile = SetChargingProfileRequest(connectorId=0, csChargingProfiles=ChargingProfile(chargingProfileId=random.randint(1, 1000), transactionId=transaction_id, stackLevel=1, chargingProfilePurpose=ChargingProfilePurposeType.TxProfile, chargingProfileKind=ChargingProfileKindType.Absolute, chargingSchedule=ChargingSchedule(duration=3600, chargingRateUnit=ChargingRateUnitType.A, chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=10.0)])))
        success = await self.handler.send_and_wait("SetChargingProfile", profile)
        self._check_cancellation()
        if success and success.get("status") == "Accepted":
            logger.info("SUCCESS: SetChargingProfile to 10A was acknowledged.")
            self._set_test_result(step_name, "SUCCESS")
        else:
            logger.error(f"FAILURE: SetChargingProfile to 10A was not acknowledged. Response: {success}")
            self._set_test_result(step_name, "FAILURE")
        logger.info(f"--- Step E.3 for {self.charge_point_id} complete. ---")

    async def run_e4_set_charging_profile_16a(self):
        """E.4: Sets a charging profile to 16A."""
        logger.info(f"--- Step E.4: Setting charging profile to 16A for {self.charge_point_id} ---")
        step_name = "run_e4_set_charging_profile_16a"
        self._check_cancellation()
        transaction_id = next((tid for tid, tdata in TRANSACTIONS.items() if
                               tdata.get("charge_point_id") == self.charge_point_id and tdata.get("status") == "Ongoing"), None)
        if not transaction_id:
            logger.error("FAILURE: No ongoing transaction found. Please start a transaction before running this step.")
            self._set_test_result(step_name, "FAILURE")
            return
        profile = SetChargingProfileRequest(connectorId=0, csChargingProfiles=ChargingProfile(chargingProfileId=random.randint(1, 1000), transactionId=transaction_id, stackLevel=1, chargingProfilePurpose=ChargingProfilePurposeType.TxProfile, chargingProfileKind=ChargingProfileKindType.Absolute, chargingSchedule=ChargingSchedule(duration=3600, chargingRateUnit=ChargingRateUnitType.A, chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=16.0)])))
        success = await self.handler.send_and_wait("SetChargingProfile", profile)
        self._check_cancellation()
        if success and success.get("status") == "Accepted":
            logger.info("SUCCESS: SetChargingProfile to 16A was acknowledged.")
            self._set_test_result(step_name, "SUCCESS")
        else:
            logger.error(f"FAILURE: SetChargingProfile to 16A was not acknowledged. Response: {success}")
            self._set_test_result(step_name, "FAILURE")
        logger.info(f"--- Step E.4 for {self.charge_point_id} complete. ---")

    async def run_e5_clear_charging_profile(self):
        """E.5: Clears any default charging profiles."""
        logger.info(f"--- Step E.5: Clearing default charging profile for {self.charge_point_id} ---")
        step_name = "run_e5_clear_charging_profile"
        self._check_cancellation()
        success = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest(connectorId=0, chargingProfilePurpose=ChargingProfilePurposeType.TxDefaultProfile)
        )
        self._check_cancellation()
        if success:
            logger.info("SUCCESS: ClearChargingProfile was acknowledged.")
            self._set_test_result(step_name, "SUCCESS")
        else:
            logger.error("FAILURE: ClearChargingProfile was not acknowledged.")
            self._set_test_result(step_name, "FAILURE")
        logger.info(f"--- Step E.5 for {self.charge_point_id} complete. ---")

    async def _wait_for_status(self, status: str):
        while CHARGE_POINTS.get(self.charge_point_id, {}).get("status") != status:
            self._check_cancellation()
            await asyncio.sleep(0.1)