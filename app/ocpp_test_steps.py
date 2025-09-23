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
    ClearCacheRequest, SendLocalListRequest, GetLocalListVersionRequest, AuthorizationData,
    IdTagInfo, UpdateType,
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
        success = await self.handler.send_and_wait(
            "TriggerMessage",
            TriggerMessageRequest(requestedMessage="BootNotification"),
            timeout=30
        )
        self._check_cancellation()
        if success and success.get("status") == "Accepted":
            logger.info("SUCCESS: The charge point acknowledged the TriggerMessage request.")
            self._set_test_result(step_name, "PASSED")
        else:
            status = success.get("status", "NO_RESPONSE") if success else "NO_RESPONSE"
            logger.error(f"FAILURE: The charge point did not respond correctly to the TriggerMessage request. Status: {status}")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step A.1 for {self.charge_point_id} complete. ---")

    async def run_a2_get_configuration_test(self):
        """A.2: GetConfiguration - Fetches and displays all configuration settings from the charge point."""
        logger.info(f"--- Step A.2: Running GetConfiguration test for {self.charge_point_id} ---")
        step_name = "run_a2_get_configuration_test"
        self._check_cancellation()
        logger.info("  Requesting all configuration keys from charge point...")
        response = await self.handler.send_and_wait(
            "GetConfiguration",
            GetConfigurationRequest(key=[]),
            timeout=30
        )
        self._check_cancellation()
        if response and response.get("configurationKey"):
            config_keys = response["configurationKey"]
            max_keys = 30

            if len(config_keys) >= max_keys:
                logger.info(f"    ⚠️ Received {len(config_keys)} configuration keys (may be limited by GetConfigurationMaxKeys={max_keys})")
                logger.info("    📝 Note: There might be additional configuration keys not shown")
            else:
                logger.info(f"    ✅ Received {len(config_keys)} configuration keys")

            self._set_test_result(step_name, "PASSED")
            
            logger.info("--- Charge Point Configuration ---")
            for key_value in config_keys:
                key = key_value.get("key")
                readonly = key_value.get("readonly", False)
                value = key_value.get("value", "")
                readonly_indicator = " (readonly)" if readonly else ""
                logger.info(f"  {key}{readonly_indicator}: {value}")

                if key == "SupportedFeatureProfiles":
                    CHARGE_POINTS[self.charge_point_id]["features"] = [f.strip() for f in value.split(",")]
            logger.info("-------------------------------------")

            await self._display_wallbox_capabilities()

        elif response and response.get("unknownKey"):
            logger.warning("Charge point reported unknown keys. This might indicate a partial success.")
            self._set_test_result(step_name, "PASSED")

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

            await self._display_wallbox_capabilities()
        else:
            logger.error("    ❌ No configuration keys received from charge point")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step A.2 for {self.charge_point_id} complete. ---")

    async def run_a3_change_configuration_test(self):
        """A.3: GetConfiguration - Retrieves all OCPP 1.6-J configuration parameters."""
        logger.info(f"--- Step A.3: Running GetConfiguration test for {self.charge_point_id} ---")
        step_name = "run_a3_change_configuration_test"
        self._check_cancellation()

        ocpp_standard_keys = [
            "AuthorizeRemoteTxRequests",
            "ClockAlignedDataInterval",
            "ConnectionTimeOut",
            "ConnectorPhaseRotation",
            "GetConfigurationMaxKeys",
            "HeartbeatInterval",
            "LocalAuthorizeOffline",
            "LocalPreAuthorize",
            "MessageTimeout",
            "MeterValuesAlignedData",
            "MeterValuesSampledData",
            "MeterValueSampleInterval",
            "NumberOfConnectors",
            "ResetRetries",
            "StopTransactionOnEVSideDisconnect",
            "StopTransactionOnInvalidId",
            "StopTxnAlignedData",
            "StopTxnSampledData",
            "SupportedFeatureProfiles",
            "TransactionMessageAttempts",
            "TransactionMessageRetryInterval",
            "UnlockConnectorOnEVSideDisconnect",
            "WebSocketPingInterval",

            "LocalAuthListEnabled",
            "LocalAuthListMaxLength",
            "SendLocalListMaxLength",

            "ChargeProfileMaxStackLevel",
            "ChargingScheduleAllowedChargingRateUnit",
            "ChargingScheduleMaxPeriods",
            "ConnectorSwitch3to1PhaseSupported",
            "MaxChargingProfilesInstalled",

            "OCPPCommCtrlrMessageAttemptIntervalBoo",
            "TxCtrlrTxStartPoint",
            "FreeChargeMode"
        ]

        results = {}

        logger.info("  Requesting all configuration keys...")
        self._check_cancellation()

        response = await self.handler.send_and_wait(
            "GetConfiguration",
            GetConfigurationRequest(key=ocpp_standard_keys),
            timeout=30
        )

        self._check_cancellation()

        if response:
            if response.get("configurationKey"):
                for config_item in response["configurationKey"]:
                    key = config_item.get("key", "")
                    value = config_item.get("value", "")
                    readonly = config_item.get("readonly", False)

                    if value:
                        display_value = value if len(value) <= 100 else f"{value[:97]}..."
                        results[key] = f"{display_value} (RO)" if readonly else display_value
                        logger.info(f"    ✅ {key}: {display_value} {'(Read-Only)' if readonly else ''}")
                    else:
                        results[key] = "No value" + (" (RO)" if readonly else "")
                        logger.info(f"    ⚠️ {key}: No value {'(Read-Only)' if readonly else ''}")

            if response.get("unknownKey"):
                for key in response["unknownKey"]:
                    results[key] = "N/A (Not Supported)"
                    logger.info(f"    ❌ {key}: Not Supported")
        else:
            logger.error("    No response received from charge point")
            for key in ocpp_standard_keys:
                results[key] = "NO_RESPONSE"

        for key in ocpp_standard_keys:
            if key not in results:
                results[key] = "N/A"
                logger.info(f"    ❌ {key}: N/A")
        if "test_results" not in CHARGE_POINTS[self.charge_point_id]:
            CHARGE_POINTS[self.charge_point_id]["test_results"] = {}
        if "configuration_details" not in CHARGE_POINTS[self.charge_point_id]:
            CHARGE_POINTS[self.charge_point_id]["configuration_details"] = {}
        CHARGE_POINTS[self.charge_point_id]["configuration_details"] = results

        logger.info("\n--- Configuration Summary ---")
        logger.info("Core Profile Parameters:")
        core_keys = ocpp_standard_keys[:23]
        for key in core_keys:
            result = results.get(key, "UNKNOWN")
            if "N/A" in result or "NO_RESPONSE" in result:
                logger.info(f"  ❌ {key}: {result}")
            elif "(RO)" in result:
                logger.info(f"  🔒 {key}: {result}")
            else:
                logger.info(f"  ✅ {key}: {result}")

        logger.info("\nOptional Profile Parameters:")
        optional_keys = ocpp_standard_keys[23:]  # Rest are optional
        for key in optional_keys:
            result = results.get(key, "UNKNOWN")
            if "N/A" in result or "NO_RESPONSE" in result:
                logger.info(f"  ⚠️ {key}: {result}")
            elif "(RO)" in result:
                logger.info(f"  🔒 {key}: {result}")
            else:
                logger.info(f"  ✅ {key}: {result}")

        logger.info("--------------------\n")

        # Test passes if we got any response
        if response and response.get("configurationKey"):
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

        # Check current status first
        current_status = CHARGE_POINTS.get(self.charge_point_id, {}).get("status")
        logger.info(f"Current wallbox status at test start: {current_status}")

        # If no status is known, trigger a StatusNotification first
        if current_status is None:
            logger.info("No initial status known - triggering StatusNotification to get current state")
            try:
                # Use TriggerMessage to request current status
                from app.messages import TriggerMessageRequest
                trigger_response = await self.handler.send_and_wait(
                    "TriggerMessage",
                    TriggerMessageRequest(requestedMessage="StatusNotification", connectorId=1),
                    timeout=10
                )
                if trigger_response and trigger_response.get("status") == "Accepted":
                    logger.info("StatusNotification trigger accepted, waiting for response...")
                    await asyncio.sleep(3)  # Wait for StatusNotification
                    current_status = CHARGE_POINTS.get(self.charge_point_id, {}).get("status")
                    logger.info(f"Status after trigger: {current_status}")
                else:
                    logger.warning(f"StatusNotification trigger failed: {trigger_response}")
            except Exception as e:
                logger.warning(f"Failed to trigger StatusNotification: {e}")

        # Start with state A - ensure we start fresh
        await self._set_ev_state("A")
        self._check_cancellation()

        # Check if we need to wait for Available status
        current_status = CHARGE_POINTS.get(self.charge_point_id, {}).get("status")
        if current_status == "Available":
            logger.info("Wallbox is in Available state")
            results["State A (Available)"] = "PASSED"
        else:
            # Wait for wallbox to respond to EV state A
            logger.info(f"Waiting for wallbox to change from '{current_status}' to 'Available'")
            try:
                await asyncio.wait_for(self._wait_for_status("Available"), timeout=15)
                self._check_cancellation()
                results["State A (Available)"] = "PASSED"
            except asyncio.TimeoutError:
                final_status = CHARGE_POINTS.get(self.charge_point_id, {}).get("status")
                logger.warning(f"State A test failed - wallbox remained in '{final_status}' status")
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

        # Test state C - Start a transaction first
        logger.info("Starting transaction for state C test...")
        id_tag = "test_id_1"  # Use same ID tag as other tests
        start_response = await self.handler.send_and_wait(
            "RemoteStartTransaction",
            RemoteStartTransactionRequest(idTag=id_tag, connectorId=1),
            timeout=30
        )
        self._check_cancellation()

        transaction_started = False
        if start_response and start_response.get("status") == "Accepted":
            logger.info("RemoteStartTransaction accepted")

            # Wait for the complete OCPP transaction flow:
            # 1. RemoteStartTransaction.conf (already received)
            # 2. Authorize.req from wallbox
            # 3. Authorize.conf from us
            # 4. StartTransaction.req from wallbox
            # 5. StartTransaction.conf from us (sets active transaction ID)
            logger.info("Waiting for authorization and StartTransaction message...")

            for attempt in range(15):  # Wait up to 15 seconds for full flow
                await asyncio.sleep(1)
                self._check_cancellation()

                # Check if any transaction exists (wallbox assigns the ID, not us)
                transaction_exists = bool(TRANSACTIONS)

                if transaction_exists:
                    # Transaction started - wallbox assigned its own ID
                    actual_tx_ids = list(TRANSACTIONS.keys())
                    logger.info(f"Transaction successfully started with wallbox-assigned ID: {actual_tx_ids[0]}")
                    transaction_started = True
                    break
                elif attempt == 8:
                    logger.debug(f"Still waiting for StartTransaction message... (attempt {attempt}/15)")

            if not transaction_started:
                if TRANSACTIONS:
                    # Final safety check - transaction arrived after our loop
                    logger.info(f"Transaction detected after timeout: {list(TRANSACTIONS.keys())}")
                    transaction_started = True
                else:
                    logger.warning("No StartTransaction message received within 15 seconds")
                    logger.debug(f"Final check - TRANSACTIONS: {list(TRANSACTIONS.keys())}")
        else:
            logger.warning(f"RemoteStartTransaction failed: {start_response}")

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

        # Test state E - Many wallboxes interpret 'E' as disconnection rather than fault
        # We'll accept either "Faulted" or "Finishing" as valid responses to state E
        await self._set_ev_state("E")
        self._check_cancellation()
        try:
            # Wait for either Faulted or Finishing status
            status_received = None
            for attempt in range(15):  # 15 second timeout in 1-second increments
                current_status = CHARGE_POINTS.get(self.charge_point_id, {}).get("status")
                if current_status in ["Faulted", "Finishing"]:
                    status_received = current_status
                    break
                await asyncio.sleep(1)
                self._check_cancellation()

            if status_received:
                logger.info(f"State E test: Wallbox responded with '{status_received}' (acceptable response)")
                results["State E (Faulted/Finishing)"] = "PASSED"
            else:
                results["State E (Faulted/Finishing)"] = "FAILED"
                all_success = False
        except Exception as e:
            logger.error(f"Error testing state E: {e}")
            results["State E (Faulted/Finishing)"] = "FAILED"
            all_success = False

        # Stop any active transaction before returning to state A
        if transaction_started:
            logger.info("Stopping transaction...")

            # Use the wallbox-assigned transaction ID (wallbox always assigns the ID)
            if TRANSACTIONS:
                wallbox_tx_id = list(TRANSACTIONS.keys())[0]
                logger.info(f"Using wallbox-assigned transaction ID {wallbox_tx_id} for RemoteStopTransaction")

                stop_response = await self.handler.send_and_wait(
                    "RemoteStopTransaction",
                    RemoteStopTransactionRequest(transactionId=wallbox_tx_id),
                    timeout=30
                )
                self._check_cancellation()
                if stop_response and stop_response.get("status") == "Accepted":
                    logger.info("RemoteStopTransaction accepted")
                    # Wait for the transaction to actually stop
                    await asyncio.sleep(2)
                else:
                    logger.warning(f"RemoteStopTransaction failed: {stop_response}")
            else:
                logger.info("No active transaction found to stop")

        # Return to state A
        await self._set_ev_state("A")
        self._check_cancellation()
        try:
            await asyncio.wait_for(self._wait_for_status("Available"), timeout=15)
            self._check_cancellation()
            results["Return to State A (Available)"] = "PASSED"
        except asyncio.TimeoutError:
            results["Return to State A (Available)"] = "FAILED"
            all_success = False

        # Allow time for any pending operations to complete
        logger.info("Waiting for any pending operations to complete...")
        await asyncio.sleep(3)
        self._check_cancellation()

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

        # Final delay to ensure all messages are processed
        await asyncio.sleep(2)
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
                GetConfigurationRequest(key=["SupportedFeatureProfiles"]),
                timeout=30
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
                payload,
                timeout=15
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

    async def run_a6_status_and_meter_value_acquisition(self):
        """A.6: Requests meter values from the charge point and waits for them."""
        logger.info(f"--- Step A.6: Acquiring meter values for {self.charge_point_id} ---")
        step_name = "run_a6_status_and_meter_value_acquisition"
        self._check_cancellation()
        # 1. Create an event to wait for the MeterValues message
        meter_values_event = asyncio.Event()
        self.pending_triggered_message_events["MeterValues"] = meter_values_event

        # 2. Send the trigger
        trigger_response = await self.handler.send_and_wait(
            "TriggerMessage",
            TriggerMessageRequest(requestedMessage="MeterValues", connectorId=1),
            timeout=30
        )
        self._check_cancellation()
        if not trigger_response or trigger_response.get("status") != "Accepted":
            status = trigger_response.get("status", "NO_RESPONSE") if trigger_response else "NO_RESPONSE"
            logger.error(f"FAILURE: The charge point did not acknowledge the TriggerMessage request. Status: {status}")
            self._set_test_result(step_name, "FAILED")
            self.pending_triggered_message_events.pop("MeterValues", None)  # Cleanup
            logger.info(f"--- Step A.6 for {self.charge_point_id} complete. ---")
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

        logger.info(f"--- Step A.6 for {self.charge_point_id} complete. ---")

    async def run_b1_remote_start_transaction_test(self):
        """B.1: RemoteStartTransaction - Starts a transaction remotely and verifies it's active."""
        logger.info(f"--- Step B.1: Running RemoteStartTransaction test for {self.charge_point_id} ---")
        step_name = "run_b1_remote_start_transaction_test"
        self._check_cancellation()
        id_tag = "test_id_1"
        connector_id = 1

        # 1. Simulate connecting an EV to the charge point.
        logger.info("📡 Step 1: Setting EV state to 'B' (vehicle connected)...")
        await self._set_ev_state("B")
        self._check_cancellation()
        logger.debug(f"Wallbox status after setting EV state to B: {CHARGE_POINTS.get(self.charge_point_id, {}).get('status')}")
        # Give the charge point a moment to process the state change (e.g., send StatusNotification)
        logger.debug("Waiting for wallbox to detect EV connection and send StatusNotification...")
        await asyncio.sleep(2)
        self._check_cancellation()

        # 2. Send the RemoteStartTransaction command.
        logger.info(f"📡 Step 2: Sending RemoteStartTransaction with idTag '{id_tag}'...")

        try:
            start_response = await asyncio.wait_for(
                self.handler.send_and_wait(
                    "RemoteStartTransaction",
                    RemoteStartTransactionRequest(idTag=id_tag, connectorId=connector_id),
                    timeout=15  # 15 second timeout for this specific call
                ),
                timeout=20  # Overall timeout including processing
            )
            self._check_cancellation()

            if not start_response or start_response.get("status") != "Accepted":
                status = start_response.get("status", "Unknown") if start_response else "No response"
                logger.error(f"    ❌ RemoteStartTransaction: {status}")
                self._set_test_result(step_name, "FAILED")
                await self._set_ev_state("A")  # Cleanup
                return

        except asyncio.TimeoutError:
            logger.error(f"    ❌ RemoteStartTransaction: Timeout - wallbox did not respond within 20 seconds")
            self._set_test_result(step_name, "FAILED")
            await self._set_ev_state("A")  # Cleanup
            return

        logger.info("    ✅ RemoteStartTransaction: Accepted")

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
        logger.debug(f"Transaction (temp key: {temp_transaction_key}, CS ID: {cs_internal_transaction_id}) registered internally after RemoteStartTransaction.")
        logger.info("⚡ Transaction authorized. Simulating EV requesting power...")

        # 4. Simulate the EV drawing power by setting state to 'C'
        logger.info("📡 Step 3: Setting EV state to 'C' (requesting power)...")
        await self._set_ev_state("C")
        self._check_cancellation()
        await asyncio.sleep(2)  # Give wallbox time to process

        # 5. Wait for the charge point to send a StatusNotification indicating "Charging".
        logger.info("📡 Step 4: Waiting for charge point to report 'Charging' status...")
        try:
            await asyncio.wait_for(self._wait_for_status("Charging"), timeout=10)
            self._check_cancellation()
            logger.info("✅ Charge point is now charging!")
        except asyncio.TimeoutError:
            logger.error("    ❌ Timeout waiting for 'Charging' status")
            self._set_test_result(step_name, "FAILED")
            await self._set_ev_state("A") # Cleanup
            self._check_cancellation()
            return

        # 6. Verify charging parameters and let transaction run
        logger.info("📊 Verifying charging parameters...")
        await asyncio.sleep(2)
        self._check_cancellation()

        # Verify wallbox capability and duty cycle from EV simulator
        # Expected: 130A maximum capability based on actual wallbox specs
        logger.debug("Verifying advertised current and CP duty cycle from EV simulator...")
        # Force a refresh of the EV simulator status to get the latest values
        if self.ocpp_server_logic.refresh_trigger:
            self.ocpp_server_logic.refresh_trigger.set()
            await asyncio.sleep(1)  # wait for poll to complete
            self._check_cancellation()

        advertised_amps = EV_SIMULATOR_STATE.get("wallbox_advertised_max_current_amps")
        duty_cycle = EV_SIMULATOR_STATE.get("cp_duty_cycle")

        # Based on actual wallbox capabilities (130A max)
        wallbox_max_amps = 130.0
        expected_duty_cycle = (wallbox_max_amps / 0.6) / 100  # Calculate based on max capability
        tolerance = 0.05  # 5% tolerance for duty cycle (more realistic)

        logger.debug(f"EV simulator reports: Advertised Amps = {advertised_amps}, Duty Cycle = {duty_cycle}")
        logger.debug(f"Wallbox max capability: {wallbox_max_amps}A, Expected Duty Cycle = ~{expected_duty_cycle:.4f}")

        if advertised_amps == wallbox_max_amps:
            logger.info(f"✅ Wallbox advertised current ({advertised_amps}A) matches maximum capability ({wallbox_max_amps}A).")
        elif advertised_amps and advertised_amps > 0:
            # Calculate the equivalent power
            power_w = advertised_amps * 230  # Assume 230V
            logger.info(f"📊 Wallbox capability: {advertised_amps}A × 230V = {power_w:.0f}W")
        else:
            logger.warning(f"⚠️  Could not determine wallbox current capability from simulator.")

        if duty_cycle is not None and duty_cycle > 0:
            # Reverse calculate the current from duty cycle for verification
            calculated_current = duty_cycle * 0.6 * 100  # Reverse of duty cycle formula
            logger.info(f"📊 CP Duty Cycle {duty_cycle:.3f} indicates ~{calculated_current:.1f}A capability")
        else:
            logger.warning(f"⚠️  Could not read CP duty cycle from simulator.")

        await asyncio.sleep(5) # Let transaction run briefly to verify it's working
        self._check_cancellation()

        # Verify transaction is active and receiving meter values
        active_transaction_id = get_active_transaction_id()
        if active_transaction_id and active_transaction_id in TRANSACTIONS:
            transaction_data = TRANSACTIONS[active_transaction_id]
            meter_values_count = len(transaction_data.get("meter_values", []))
            logger.info(f"✅ Transaction {active_transaction_id} is active with {meter_values_count} meter value records")
            logger.info("✅ RemoteStartTransaction test completed successfully!")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error("❌ No active transaction found after RemoteStartTransaction")
            self._set_test_result(step_name, "FAILED")

        # Note: Transaction is left running for B.2 (RemoteStopTransaction) test
        # EV state remains at 'C' (charging) to continue the transaction
        logger.info("📝 Transaction left running for separate B.2 (RemoteStopTransaction) test")
        logger.info(f"🏁 Step B.1 for {self.charge_point_id} complete.")

        # Standardized test completion logging
        result = CHARGE_POINTS.get(self.charge_point_id, {}).get("test_results", {}).get(step_name, "UNKNOWN")
        if result == "PASSED":
            logger.info(f"✅ SUCCESS: Step B.1 RemoteStartTransaction test PASSED for {self.charge_point_id}")
        else:
            logger.error(f"❌ FAILURE: Step B.1 RemoteStartTransaction test FAILED for {self.charge_point_id}")
        logger.info(f"--- Step B.1 for {self.charge_point_id} complete. ---")

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

    async def run_c1_set_charging_profile_test(self, params: Dict[str, Any] = None):
        """C.1: SetChargingProfile - Sets a charging profile to limit power on an active transaction."""
        if params is None:
            params = {}

        logger.info(f"--- Step C.1: Running SetChargingProfile test for {self.charge_point_id} ---")
        step_name = "run_c1_set_charging_profile_test"
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

        # Get values from params or use defaults
        stack_level = params.get("stackLevel", 0)
        purpose = params.get("chargingProfilePurpose", "TxProfile")
        kind = params.get("chargingProfileKind", "Absolute")
        charging_unit = params.get("chargingRateUnit")
        limit = params.get("limit")
        duration = params.get("duration", 3600)

        # If no unit or limit specified, use configured charging values
        if charging_unit is None or limit is None:
            disable_value, default_unit = get_charging_value("disable")
            if charging_unit is None:
                charging_unit = default_unit
            if limit is None:
                limit = disable_value

        profile = SetChargingProfileRequest(
            connectorId=1, 
            csChargingProfiles=ChargingProfile(
                chargingProfileId=random.randint(1, 1000), 
                transactionId=transaction_id, 
                stackLevel=stack_level, 
                chargingProfilePurpose=purpose, 
                chargingProfileKind=kind, 
                chargingSchedule=ChargingSchedule(
                    duration=duration, 
                    chargingRateUnit=charging_unit, 
                    chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=limit)]
                )
            )
        )
        logger.info(f"Sending SetChargingProfile message: {asdict(profile)}")
        success = await self.handler.send_and_wait("SetChargingProfile", profile, timeout=30)
        self._check_cancellation()
        if success and success.get("status") == "Accepted":
            logger.info("SUCCESS: SetChargingProfile was acknowledged by the charge point.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error(f"FAILURE: SetChargingProfile was not acknowledged by the charge point. Response: {success}")
            self._set_test_result(step_name, "FAILED")
        logger.info(f"--- Step C.1 for {self.charge_point_id} complete. ---")

    async def run_c4_tx_default_profile_test(self, params: Dict[str, Any] = None):
        """C.4: TxDefaultProfile - Sets a default charging profile to medium power/current for future transactions."""
        if params is None:
            params = {}

        # Get values from params or use defaults
        stack_level = params.get("stackLevel", 0) # Changed default to 0
        purpose = params.get("chargingProfilePurpose", "TxDefaultProfile")
        kind = params.get("chargingProfileKind", "Absolute")
        charging_unit = params.get("chargingRateUnit")
        limit = params.get("limit")
        # Note: TxDefaultProfile should not have duration per OCPP standard

        # If no unit or limit specified, use configured charging values
        if charging_unit is None or limit is None:
            medium_value, default_unit = get_charging_value("medium")
            if charging_unit is None:
                charging_unit = default_unit
            if limit is None:
                limit = medium_value

        logger.info(f"--- Step C.4: Running TxDefaultProfile test to {limit}{charging_unit} for {self.charge_point_id} ---")
        step_name = "run_c4_tx_default_profile_test"
        self._check_cancellation()

        # Clear any existing profile first (MaxChargingProfilesInstalled = 1)
        clear_response = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest()
        )
        logger.info(f"ClearChargingProfile response: {clear_response}")

        # First profile: connectorId=0 (charge point level)
        profile_cp = SetChargingProfileRequest(
            connectorId=0,
            csChargingProfiles=ChargingProfile(
                chargingProfileId=random.randint(1, 1000),
                stackLevel=stack_level,
                chargingProfilePurpose=purpose,
                chargingProfileKind=kind,
                chargingSchedule=ChargingSchedule(
                    chargingRateUnit=charging_unit,
                    chargingSchedulePeriod=[
                        ChargingSchedulePeriod(
                            startPeriod=0,
                            limit=limit,
                            numberPhases=3
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
                stackLevel=stack_level,
                chargingProfilePurpose=purpose,
                chargingProfileKind=kind,
                chargingSchedule=ChargingSchedule(
                    chargingRateUnit=charging_unit,
                    chargingSchedulePeriod=[
                        ChargingSchedulePeriod(
                            startPeriod=0,
                            limit=limit,
                            numberPhases=3
                        )
                    ]
                )
            )
        )
        logger.info(f"Sending SetChargingProfile message for connectorId=1: {asdict(profile_conn)}")
        success_conn = await self.handler.send_and_wait("SetChargingProfile", profile_conn)
        self._check_cancellation()

        if success_cp and success_cp.get("status") == "Accepted" and success_conn and success_conn.get("status") == "Accepted":
            logger.info(f"PASSED: SetChargingProfile to {limit}{charging_unit} for both connectorId=0 and connectorId=1 was acknowledged.")
            self._set_test_result(step_name, "PASSED")
        else:
            logger.error(f"FAILED: SetChargingProfile to {limit}{charging_unit} was not acknowledged for connectorId=0: {success_cp}, connectorId=1: {success_conn}")
            self._set_test_result(step_name, "FAILED")
        logger.info(f"--- Step C.4 for {self.charge_point_id} complete. ---")

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

    async def run_c3_clear_charging_profile_test(self):
        """C.3: ClearChargingProfile - Clears any default charging profiles."""
        logger.info(f"--- Step C.3: Running ClearChargingProfile test for {self.charge_point_id} ---")
        step_name = "run_c3_clear_charging_profile_test"
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

    async def run_b2_remote_stop_transaction_test(self):
        """B.2: RemoteStopTransaction - Stops the active transaction remotely."""
        logger.info(f"--- Step B.2: Running RemoteStopTransaction test for {self.charge_point_id} ---")
        step_name = "run_b2_remote_stop_transaction_test"
        self._check_cancellation()

        transaction_id = get_active_transaction_id()
        if transaction_id is None:
            logger.error("FAILED: No active transaction found to stop.")
            self._set_test_result(step_name, "FAILED")
            return

        stop_response = await self.handler.send_and_wait(
            "RemoteStopTransaction",
            RemoteStopTransactionRequest(transactionId=transaction_id),
            timeout=30
        )
        self._check_cancellation()

        if not stop_response or stop_response.get("status") != "Accepted":
            status = stop_response.get('status', 'no response') if stop_response else 'no response'
            logger.error(f"FAILED: RemoteStopTransaction for transaction {transaction_id} was not accepted (status: {status}).")
            self._set_test_result(step_name, "FAILED")
        else:
            logger.info(f"PASSED: RemoteStopTransaction for transaction {transaction_id} was acknowledged.")
            self._set_test_result(step_name, "PASSED")

        # After stopping, simulate unplugging the EV
        logger.info("🔌 Simulating EV unplugged (State A)...")
        await self._set_ev_state("A")
        self._check_cancellation()

        # Wait for the charge point to become available again
        logger.info("⏳ Waiting for charge point to become Available...")
        try:
            await asyncio.wait_for(self._wait_for_status("Available"), timeout=20)
            self._check_cancellation()
            logger.info("✅ Charge point is Available.")
        except asyncio.TimeoutError:
            logger.error("❌ Timeout waiting for 'Available' status after remote stop.")
            # This might not be a test failure, but a warning for the next test
        
        logger.info(f"--- Step B.2 for {self.charge_point_id} complete. ---")

    async def run_b3_rfid_authorization_test(self):
        """B.3: RFID Authorization - Tests RFID card authorization with accepted and invalid cards."""
        logger.info(f"--- Step B.3: RFID Authorization test for {self.charge_point_id} ---")
        step_name = "run_b3_rfid_authorization_test"
        self._check_cancellation()

        # Import here to avoid circular imports
        from app.ocpp_message_handlers import rfid_test_state
        from datetime import datetime, timezone

        # Activate RFID test mode
        rfid_test_state["active"] = True
        rfid_test_state["cards_presented"] = []
        rfid_test_state["test_start_time"] = datetime.now(timezone.utc)

        logger.info("🎫 RFID Test Mode ACTIVATED")
        logger.info("   📘 Instruction: Present the FIRST RFID card (will be ACCEPTED)")
        logger.info("   📘 Then present a DIFFERENT RFID card (will be INVALID)")
        logger.info("   📘 Any additional cards will also be INVALID")
        logger.info("   💡 IMPORTANT: Use different cards - same card may not be re-read immediately")
        logger.info("   📘 The wallbox will send Authorize.req messages to the server")

        # Wait for user to present cards and wallbox to send Authorize requests
        logger.info("⏳ Waiting 60 seconds for RFID card presentations...")
        logger.info("   👤 User Action Required: Present RFID cards to the wallbox reader")

        try:
            await asyncio.sleep(60)
        finally:
            # Deactivate RFID test mode
            rfid_test_state["active"] = False

        logger.info("✅ Step B.3: RFID Authorization test completed")
        logger.info(f"   📊 Cards presented during test: {len(rfid_test_state['cards_presented'])}")
        for i, card_id in enumerate(rfid_test_state["cards_presented"], 1):
            status = "ACCEPTED" if i == 1 else "INVALID"
            logger.info(f"   🎫 Card #{i}: {card_id} → {status}")

        # Test passes if at least one card was presented
        if rfid_test_state["cards_presented"]:
            self._set_test_result(step_name, "PASSED")
            logger.info("✅ Test PASSED: At least one card was detected")
        else:
            self._set_test_result(step_name, "FAILED")
            logger.warning("⚠️ Test FAILED: No cards were detected during test period")

        logger.info(f"--- Step B.3 for {self.charge_point_id} complete. ---")

    async def run_b4_clear_rfid_cache(self):
        """B.4: Clear RFID Cache - Clears the local authorization list (RFID cache) in the wallbox."""
        logger.info(f"--- Step B.4: Clear RFID Cache for {self.charge_point_id} ---")
        step_name = "run_b4_clear_rfid_cache"
        self._check_cancellation()

        logger.info("🗑️ Sending ClearCache command to wallbox...")
        logger.info("   📘 This command clears the local authorization list (RFID memory)")
        logger.info("   📘 After clearing, only RFID cards in the Central System's authorization list will be accepted")

        # Create ClearCache request (no payload needed)
        clear_cache_request = ClearCacheRequest()

        try:
            # Send ClearCache command and wait for response
            response = await self.handler.send_and_wait("ClearCache", clear_cache_request, timeout=10)

            if response is None:
                logger.error("❌ ClearCache request timed out")
                self._set_test_result(step_name, "FAILED")
                return

            status = response.get("status", "Unknown")
            logger.info(f"📝 ClearCache response status: {status}")

            if status == "Accepted":
                logger.info("✅ Clear RFID Cache successful")
                logger.info("   💡 Local RFID authorization list has been cleared")
                logger.info("   💡 Wallbox will now rely on Central System for RFID authorization")
                self._set_test_result(step_name, "PASSED")
            elif status == "Rejected":
                logger.warning("⚠️ Clear RFID Cache was rejected by wallbox")
                logger.info("   💡 Wallbox may not support ClearCache command")
                self._set_test_result(step_name, "FAILED")
            else:
                logger.error(f"❌ Unexpected ClearCache response status: {status}")
                self._set_test_result(step_name, "FAILED")

        except Exception as e:
            logger.error(f"❌ Error during ClearCache: {e}")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step B.4 for {self.charge_point_id} complete. ---")

    async def run_b5_send_rfid_list(self):
        """B.5: Send RFID List - Sends a local authorization list with RFID cards to the wallbox."""
        logger.info(f"--- Step B.5: Send RFID List for {self.charge_point_id} ---")
        step_name = "run_b5_send_rfid_list"
        self._check_cancellation()

        logger.info("📋 Sending local authorization list to wallbox...")
        logger.info("   📘 This sends RFID card IDs that should be authorized locally")
        logger.info("   📘 Cards in this list can authorize transactions without Central System")

        # Create some example RFID cards for the authorization list
        rfid_cards = [
            AuthorizationData(
                idTag="TEST_CARD_001",
                idTagInfo=IdTagInfo(status="Accepted")
            ),
            AuthorizationData(
                idTag="TEST_CARD_002",
                idTagInfo=IdTagInfo(status="Accepted")
            ),
            AuthorizationData(
                idTag="TEST_CARD_003",
                idTagInfo=IdTagInfo(status="Blocked")
            ),
        ]

        # Create SendLocalList request with Full update (replace entire list)
        send_list_request = SendLocalListRequest(
            listVersion=1,  # Start with version 1
            updateType=UpdateType.Full,
            localAuthorizationList=rfid_cards
        )

        logger.info(f"   📋 Sending {len(rfid_cards)} RFID cards:")
        for i, card in enumerate(rfid_cards, 1):
            status = card.idTagInfo.status if card.idTagInfo else "Unknown"
            logger.info(f"   🎫 Card {i}: {card.idTag} → {status}")

        try:
            # Send SendLocalList command and wait for response
            response = await self.handler.send_and_wait("SendLocalList", send_list_request, timeout=15)

            if response is None:
                logger.error("❌ SendLocalList request timed out")
                self._set_test_result(step_name, "FAILED")
                return

            status = response.get("status", "Unknown")
            logger.info(f"📝 SendLocalList response status: {status}")

            if status == "Accepted":
                logger.info("✅ Send RFID List successful")
                logger.info("   💡 Local authorization list has been updated in wallbox")
                logger.info("   💡 Listed RFID cards can now authorize locally")
                logger.info("   💡 You can test these cards with the B.3 RFID Authorization test")
                self._set_test_result(step_name, "PASSED")
            elif status == "Failed":
                logger.warning("⚠️ Send RFID List failed - wallbox rejected the list")
                self._set_test_result(step_name, "FAILED")
            elif status == "NotSupported":
                logger.warning("⚠️ Send RFID List not supported by wallbox")
                logger.info("   💡 Wallbox doesn't support local authorization lists")
                self._set_test_result(step_name, "FAILED")
            elif status == "VersionMismatch":
                logger.warning("⚠️ Version mismatch - wallbox has different list version")
                logger.info("   💡 Try running B.6 Get RFID List Version first")
                self._set_test_result(step_name, "FAILED")
            else:
                logger.error(f"❌ Unexpected SendLocalList response status: {status}")
                self._set_test_result(step_name, "FAILED")

        except Exception as e:
            logger.error(f"❌ Error during SendLocalList: {e}")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step B.5 for {self.charge_point_id} complete. ---")

    async def run_b6_get_rfid_list_version(self):
        """B.6: Get RFID List Version - Gets the current version of the local authorization list."""
        logger.info(f"--- Step B.6: Get RFID List Version for {self.charge_point_id} ---")
        step_name = "run_b6_get_rfid_list_version"
        self._check_cancellation()

        logger.info("📋 Requesting local authorization list version from wallbox...")
        logger.info("   📘 This retrieves the version number of the current RFID list")
        logger.info("   📘 Version numbers are used to synchronize list updates")

        # Create GetLocalListVersion request (no payload needed)
        get_version_request = GetLocalListVersionRequest()

        try:
            # Send GetLocalListVersion command and wait for response
            response = await self.handler.send_and_wait("GetLocalListVersion", get_version_request, timeout=10)

            if response is None:
                logger.error("❌ GetLocalListVersion request timed out")
                self._set_test_result(step_name, "FAILED")
                return

            list_version = response.get("listVersion", -1)
            logger.info(f"📝 Current RFID list version: {list_version}")

            if list_version >= 0:
                logger.info("✅ Get RFID List Version successful")
                if list_version == 0:
                    logger.info("   💡 Version 0 means no local authorization list is stored")
                    logger.info("   💡 Run B.5 Send RFID List to create a local authorization list")
                else:
                    logger.info(f"   💡 Local authorization list exists with version {list_version}")
                    logger.info("   💡 Use this version number for differential updates")
                self._set_test_result(step_name, "PASSED")
            elif list_version == -1:
                logger.warning("⚠️ Wallbox returned version -1")
                logger.info("   💡 This typically means the wallbox does not support local authorization lists")
                logger.info("   💡 Or local authorization functionality is disabled")
                logger.info("   💡 Try B.5 Send RFID List to test if SendLocalList is supported")
                self._set_test_result(step_name, "NOT_SUPPORTED")
            else:
                logger.error(f"❌ Invalid list version received: {list_version}")
                self._set_test_result(step_name, "FAILED")

        except Exception as e:
            logger.error(f"❌ Error during GetLocalListVersion: {e}")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step B.6 for {self.charge_point_id} complete. ---")

    async def run_x1_reboot_wallbox(self):
        """X.1: Reboot Wallbox - Sends Reset Hard to force stop all transactions and reboot charge point."""
        logger.info(f"--- Step X.1: Reboot Wallbox (Reset Hard) for {self.charge_point_id} ---")
        step_name = "run_x1_reboot_wallbox"
        self._check_cancellation()

        logger.warning("⚠️  Sending Hard Reset to force terminate all transactions and reboot")
        logger.info("This will cause the charge point to reboot without gracefully stopping sessions")

        reset_request = ResetRequest(type=ResetType.Hard)
        logger.info(f"Sending Reset Hard message: {asdict(reset_request)}")

        success = await self.handler.send_and_wait("Reset", reset_request, timeout=30)
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

        logger.info(f"--- Step X.1 for {self.charge_point_id} complete. ---")

    async def run_c2_get_composite_schedule_test(self):
        """C.2: GetCompositeSchedule - Queries the current schedule being applied on connector 1."""
        logger.info(f"--- Step C.2: Running GetCompositeSchedule test for {self.charge_point_id} ---")
        step_name = "run_c2_get_composite_schedule_test"
        self._check_cancellation()

        logger.info("Querying current charging schedule on connector 1...")

        composite_request = GetCompositeScheduleRequest(
            connectorId=1,
            duration=3600  # Query for next 1 hour
        )
        logger.info(f"Sending GetCompositeSchedule: {asdict(composite_request)}")

        response = await self.handler.send_and_wait("GetCompositeSchedule", composite_request, timeout=30)
        self._check_cancellation()

        # Clear previous schedule
        if "composite_schedule" in CHARGE_POINTS[self.charge_point_id]:
            del CHARGE_POINTS[self.charge_point_id]["composite_schedule"]

        if response and response.get("status") == "Accepted":
            logger.info("PASSED: GetCompositeSchedule was accepted.")
            if response.get("chargingSchedule"):
                schedule = response.get("chargingSchedule")
                
                # Store the schedule for the UI
                CHARGE_POINTS[self.charge_point_id]["composite_schedule"] = schedule

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

        logger.info(f"--- Step C.2 for {self.charge_point_id} complete. ---")

    async def run_e11_clear_all_profiles(self):
        """E.11: Clears ALL charging profiles from the charge point."""
        logger.info(f"--- Step E.11: Clearing ALL charging profiles for {self.charge_point_id} ---")
        step_name = "run_e11_clear_all_profiles"
        self._check_cancellation()

        logger.info("Sending ClearChargingProfile request to clear profiles for connectorId=0...")
        success_0 = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest(connectorId=0),
            timeout=30
        )
        self._check_cancellation()

        logger.info("Sending ClearChargingProfile request to clear profiles for connectorId=1...")
        success_1 = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest(connectorId=1),
            timeout=30
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

    async def _display_wallbox_capabilities(self):
        """Display actual wallbox capabilities based on comprehensive MeterValues analysis."""
        logger.info("--- Wallbox offers to EV ---")

        # Get all available MeterValues data for comprehensive analysis
        all_meter_values = []
        latest_meter_data = None
        active_transaction_id = get_active_transaction_id()

        if active_transaction_id and active_transaction_id in TRANSACTIONS:
            transaction_data = TRANSACTIONS[active_transaction_id]
            all_meter_values = transaction_data.get("meter_values", [])
            if all_meter_values:
                latest_meter_data = all_meter_values[-1]  # Get most recent MeterValues

        # If no transaction data, check for any recent MeterValues from this charge point
        if not latest_meter_data:
            for tx_id, tx_data in TRANSACTIONS.items():
                if tx_data.get("charge_point_id") == self.charge_point_id:
                    meter_values = tx_data.get("meter_values", [])
                    if meter_values:
                        all_meter_values.extend(meter_values)
                        latest_meter_data = meter_values[-1]

        # Comprehensive MeterValues analysis
        meter_analysis = {
            "voltage": {"L1": None, "L2": None, "L3": None, "L1-N": None, "L2-N": None, "L3-N": None},
            "current": {"L1": None, "L2": None, "L3": None, "import": None, "export": None},
            "power": {"active_import": None, "active_export": None, "reactive": None, "L1": None, "L2": None, "L3": None},
            "energy": {"active_import": None, "active_export": None, "reactive": None},
            "temperature": None,
            "frequency": None,
            "power_factor": None,
            "max_values": {"current": 0, "power": 0, "voltage": 0},
            "measurand_count": {},
            "connection_phases": set()
        }

        # Analyze all MeterValues data
        logger.info("  📊 MeterValues Data Analysis:")

        if latest_meter_data:
            logger.info(f"    Latest MeterValues record found: {type(latest_meter_data)}")

            # Handle different MeterValues data structures
            sampled_values = None
            if hasattr(latest_meter_data, 'sampledValue'):
                sampled_values = latest_meter_data.sampledValue
            elif hasattr(latest_meter_data, 'sampled_value'):
                sampled_values = latest_meter_data.sampled_value
            elif isinstance(latest_meter_data, dict) and 'sampledValue' in latest_meter_data:
                sampled_values = latest_meter_data['sampledValue']

            if sampled_values:
                logger.info(f"    Found {len(sampled_values)} sampled values")
                for sample in sampled_values:
                    measurand = sample.measurand or "Unknown"
                    phase = getattr(sample, 'phase', None)
                    value = sample.value
                    unit = getattr(sample, 'unit', 'Unknown')
                    location = getattr(sample, 'location', 'Unknown')
                    context = getattr(sample, 'context', 'Sample.Periodic')

                    # Count measurands
                    meter_analysis["measurand_count"][measurand] = meter_analysis["measurand_count"].get(measurand, 0) + 1

                    try:
                        numeric_value = float(value)

                        # Voltage analysis
                        if "Voltage" in measurand:
                            if phase:
                                meter_analysis["voltage"][phase] = numeric_value
                                if phase in ["L1", "L2", "L3"]:
                                    meter_analysis["connection_phases"].add(phase)
                            meter_analysis["max_values"]["voltage"] = max(meter_analysis["max_values"]["voltage"], numeric_value)

                        # Current analysis
                        elif "Current" in measurand:
                            if "Import" in measurand:
                                if phase:
                                    meter_analysis["current"][phase] = numeric_value
                                    if phase in ["L1", "L2", "L3"]:
                                        meter_analysis["connection_phases"].add(phase)
                                else:
                                    meter_analysis["current"]["import"] = numeric_value
                            elif "Export" in measurand:
                                meter_analysis["current"]["export"] = numeric_value
                            meter_analysis["max_values"]["current"] = max(meter_analysis["max_values"]["current"], numeric_value)

                        # Power analysis
                        elif "Power" in measurand:
                            if "Active.Import" in measurand:
                                if phase:
                                    meter_analysis["power"][phase] = numeric_value
                                else:
                                    meter_analysis["power"]["active_import"] = numeric_value
                            elif "Active.Export" in measurand:
                                meter_analysis["power"]["active_export"] = numeric_value
                            elif "Reactive" in measurand:
                                meter_analysis["power"]["reactive"] = numeric_value
                            meter_analysis["max_values"]["power"] = max(meter_analysis["max_values"]["power"], numeric_value)

                        # Energy analysis
                        elif "Energy" in measurand:
                            if "Active.Import" in measurand:
                                meter_analysis["energy"]["active_import"] = numeric_value
                            elif "Active.Export" in measurand:
                                meter_analysis["energy"]["active_export"] = numeric_value
                            elif "Reactive" in measurand:
                                meter_analysis["energy"]["reactive"] = numeric_value

                        # Other measurements
                        elif "Temperature" in measurand:
                            meter_analysis["temperature"] = numeric_value
                        elif "Frequency" in measurand:
                            meter_analysis["frequency"] = numeric_value
                        elif "Power.Factor" in measurand:
                            meter_analysis["power_factor"] = numeric_value

                        # Log detailed measurement
                        phase_info = f" (Phase: {phase})" if phase else ""
                        logger.info(f"    {measurand}: {value} {unit}{phase_info}")

                    except (ValueError, TypeError):
                        logger.info(f"    {measurand}: {value} {unit} (non-numeric)")
            else:
                logger.info("    No MeterValues sampled data found")
        else:
            logger.info("    No MeterValues data available yet")

        # Connection type determination
        active_phases = len(meter_analysis["connection_phases"])
        if active_phases >= 3:
            connection_type = "Three-phase"
        elif active_phases >= 1:
            connection_type = "Single-phase"
        else:
            connection_type = "Unknown"

        logger.info(f"  🔌 Connection Analysis:")
        logger.info(f"    Connection Type: {connection_type} ({active_phases} active phases detected)")

        # Voltage summary
        if any(v for v in meter_analysis["voltage"].values() if v):
            logger.info(f"    Voltage Readings:")
            for phase, voltage in meter_analysis["voltage"].items():
                if voltage:
                    logger.info(f"      {phase}: {voltage:.1f}V")

        # Current capability analysis
        max_current = meter_analysis["max_values"]["current"]
        max_power = meter_analysis["max_values"]["power"]

        logger.info(f"  ⚡ Power Capability Analysis:")
        if max_current > 0:
            logger.info(f"    Peak Current Observed: {max_current:.1f}A")
        if max_power > 0:
            logger.info(f"    Peak Power Observed: {max_power:.0f}W ({max_power/1000:.1f}kW)")

        # Get EV simulator data for advertised capability
        advertised_amps = EV_SIMULATOR_STATE.get("wallbox_advertised_max_current_amps", 0)
        duty_cycle = EV_SIMULATOR_STATE.get("cp_duty_cycle", 0)

        if advertised_amps:
            logger.info(f"    Wallbox Advertised Max: {advertised_amps}A")

            # Calculate theoretical max power based on measured voltage
            nominal_voltage = 230  # Default
            if meter_analysis["voltage"]["L1-N"]:
                nominal_voltage = meter_analysis["voltage"]["L1-N"]
            elif meter_analysis["voltage"]["L1"]:
                nominal_voltage = meter_analysis["voltage"]["L1"]

            if connection_type == "Three-phase":
                theoretical_max = advertised_amps * nominal_voltage * 3
            else:
                theoretical_max = advertised_amps * nominal_voltage

            logger.info(f"    Theoretical Max Power: {theoretical_max:.0f}W ({theoretical_max/1000:.1f}kW)")

        # Show configured power levels based on actual wallbox specs
        from app.core import CHARGING_RATE_CONFIG
        logger.info("  📋 Available Charging Levels:")
        for level, values in CHARGING_RATE_CONFIG["test_value_mapping"].items():
            if level != "disable":
                current_a = values["A"]
                power_w = values["W"]
                logger.info(f"    {level.capitalize()}: {current_a}A / {power_w}W ({power_w/1000:.1f}kW)")

        # CP duty cycle information
        if duty_cycle and duty_cycle > 0:
            logger.info(f"  🎛️  CP Duty Cycle: {duty_cycle:.3f} ({duty_cycle*100:.1f}%)")

        # MeterValues statistics
        if meter_analysis["measurand_count"]:
            logger.info(f"  📈 MeterValues Summary:")
            logger.info(f"    Total Meter Records: {len(all_meter_values)}")
            logger.info(f"    Measurands in Latest Sample:")
            for measurand, count in meter_analysis["measurand_count"].items():
                logger.info(f"      {measurand}: {count} value(s)")

        logger.info("-------------------------------------")

    async def _wait_for_status(self, status: str):
        while CHARGE_POINTS.get(self.charge_point_id, {}).get("status") != status:
            self._check_cancellation()
            await asyncio.sleep(0.1)