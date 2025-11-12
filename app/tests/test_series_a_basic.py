"""
OCPP Test Series A: Core Communication & Status

Tests basic OCPP protocol functionality:
- A.1: Initial Registration
- A.2: Get All Configuration Parameters
- A.3: Check Single Parameters
- A.4: Check Initial State
- A.5: Trigger All Messages
- A.6: Status and Meter Value Acquisition
"""

import asyncio
import logging
from dataclasses import asdict

from app.core import (
    CHARGE_POINTS, TRANSACTIONS, SERVER_SETTINGS, OCPP_MESSAGE_TIMEOUT,
    EV_SIMULATOR_STATE, get_active_transaction_id
)
from app.messages import (
    BootNotificationRequest, TriggerMessageRequest, GetConfigurationRequest,
    RemoteStartTransactionRequest, RemoteStopTransactionRequest
)
from app.tests.test_base import OcppTestBase

logger = logging.getLogger(__name__)


class TestSeriesA(OcppTestBase):
    """Test Series A: Core Communication & Status (6 tests)"""

    async def run_a1_initial_registration(self):
        """A.1: Verifies that the charge point has registered itself."""
        logger.info(f"--- Step A.1: Verifying initial registration for {self.charge_point_id} ---")
        step_name = "run_a1_initial_registration"
        self._check_cancellation()
        success = await self.handler.send_and_wait(
            "TriggerMessage",
            TriggerMessageRequest(requestedMessage="BootNotification"),
            timeout=OCPP_MESSAGE_TIMEOUT
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

    async def run_a2_get_all_parameters(self):
        """A.2: Get All Configuration - Retrieves all configuration keys using GetConfiguration with empty key array.

        Per OCPP 1.6-J specification: Empty key array requests ALL available configuration parameters.
        May be limited by GetConfigurationMaxKeys parameter.
        """
        logger.info(f"--- Step A.2: Get All Configuration for {self.charge_point_id} ---")
        step_name = "run_a2_get_all_parameters"
        self._check_cancellation()

        logger.info("  Requesting ALL configuration keys (empty key array)...")

        try:
            # Send GetConfiguration with EMPTY key array to get all parameters
            response = await self.handler.send_and_wait(
                "GetConfiguration",
                GetConfigurationRequest(key=[]),  # Empty array = get ALL
                timeout=OCPP_MESSAGE_TIMEOUT
            )

            if response and response.get("configurationKey"):
                config_keys = response["configurationKey"]
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

                # Check if response was limited by GetConfigurationMaxKeys
                unknown_keys = response.get("unknownKey", [])
                if unknown_keys:
                    logger.warning(f"    ⚠️  {len(unknown_keys)} keys marked as unknown")

                # Note if results may be limited
                max_keys_value = None
                for key_value in config_keys:
                    if key_value.get("key") == "GetConfigurationMaxKeys":
                        max_keys_value = key_value.get("value")
                        break

                if max_keys_value:
                    logger.info(f"  ℹ️  GetConfigurationMaxKeys: {max_keys_value}")
                    logger.info(f"  ℹ️  Results may be limited to {max_keys_value} keys per request")

                await self._display_wallbox_capabilities()
            else:
                logger.error("    ❌ No configuration keys received from charge point")
                logger.error("    ℹ️  Charge point may not support empty key array request")
                self._set_test_result(step_name, "FAILED")

        except Exception as e:
            logger.error(f"    ❌ Error requesting configuration: {e}")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step A.2 for {self.charge_point_id} complete. ---")

    async def run_a3_check_single_parameters(self):
        """A.3: Check single Parameters - Retrieves all OCPP 1.6-J standard configuration parameters by explicitly requesting each key."""
        logger.info(f"--- Step A.3: Running GetConfiguration test for {self.charge_point_id} ---")
        step_name = "run_a3_check_single_parameters"
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

        logger.info(f"  Sending {len(ocpp_standard_keys)} GetConfiguration requests with sliding window (max 5 concurrent)...")
        logger.info("  (Optimized: Keep 5 requests in flight, send next one as soon as one completes)")

        # Helper function to request a single key
        async def request_key(key: str):
            try:
                response = await self.handler.send_and_wait(
                    "GetConfiguration",
                    GetConfigurationRequest(key=[key]),
                    timeout=5  # 5 second timeout per request
                )

                if response:
                    if response.get("configurationKey"):
                        config_item = response["configurationKey"][0]
                        value = config_item.get("value", "")
                        readonly = config_item.get("readonly", False)

                        if value:
                            display_value = value if len(value) <= 100 else f"{value[:97]}..."
                            result_value = f"{display_value} (RO)" if readonly else display_value
                            logger.info(f"    ✅ {key}: {display_value}" + (" (RO)" if readonly else ""))
                            return (key, result_value)
                        else:
                            result_value = "No value" + (" (RO)" if readonly else "")
                            logger.info(f"    ⚠️  {key}: No value" + (" (RO)" if readonly else ""))
                            return (key, result_value)

                    elif response.get("unknownKey"):
                        logger.info(f"    ❌ {key}: Not Supported")
                        return (key, "N/A (Not Supported)")
                    else:
                        logger.info(f"    ❌ {key}: N/A")
                        return (key, "N/A")
                else:
                    logger.warning(f"    ⏱️  {key}: No response")
                    return (key, "NO_RESPONSE")

            except Exception as e:
                logger.error(f"    ❌ {key}: Error - {e}")
                return (key, f"ERROR: {str(e)}")

        # Sliding window approach: maintain exactly 5 concurrent requests
        MAX_CONCURRENT = 5
        pending_tasks = set()
        key_index = 0

        # Start initial batch of 5 requests
        while key_index < len(ocpp_standard_keys) and len(pending_tasks) < MAX_CONCURRENT:
            task = asyncio.create_task(request_key(ocpp_standard_keys[key_index]))
            pending_tasks.add(task)
            key_index += 1

        # Process requests: as soon as one completes, start the next one
        while pending_tasks:
            # Wait for at least one task to complete
            done, pending_tasks = await asyncio.wait(pending_tasks, return_when=asyncio.FIRST_COMPLETED)

            # Collect results from completed tasks
            for task in done:
                key, value = await task
                results[key] = value

            # Start new tasks to maintain MAX_CONCURRENT in flight
            while key_index < len(ocpp_standard_keys) and len(pending_tasks) < MAX_CONCURRENT:
                task = asyncio.create_task(request_key(ocpp_standard_keys[key_index]))
                pending_tasks.add(task)
                key_index += 1

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

        # Test passes if we got any successful responses (not N/A or NO_RESPONSE)
        successful_results = [v for v in results.values() if "N/A" not in v and "NO_RESPONSE" not in v and "ERROR" not in v]
        if successful_results:
            self._set_test_result(step_name, "PASSED")
        else:
            self._set_test_result(step_name, "FAILED", "No successful responses received")

        logger.info(f"--- Step A.3 for {self.charge_point_id} complete. ---")

    async def run_a4_check_initial_state(self):
        """A.4: Checks the initial status of the charge point."""
        logger.info(f"--- Step A.4: Checking initial state for {self.charge_point_id} ---")
        step_name = "run_a4_check_initial_state"
        self._check_cancellation()
        if not SERVER_SETTINGS.get("ev_simulator_available"):
            logger.warning("Skipping test: EV simulator is not in use.")
            self._set_test_result(
                step_name,
                "SKIPPED",
                "Test requires EV simulator. Connect and enable the EV simulator to run this test."
            )
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
                    timeout=OCPP_MESSAGE_TIMEOUT
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
        id_tag = "50600020100021"  # Use same ID tag as other tests
        start_response = await self.handler.send_and_wait(
            "RemoteStartTransaction",
            RemoteStartTransactionRequest(idTag=id_tag, connectorId=1),
            timeout=OCPP_MESSAGE_TIMEOUT
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
                    timeout=OCPP_MESSAGE_TIMEOUT
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
                timeout=OCPP_MESSAGE_TIMEOUT
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

        # Define messages to trigger with their parameters
        triggered_messages = {
            "StatusNotification": {"connectorId": 1},
            "BootNotification": {},
            "DiagnosticsStatusNotification": {},
            "FirmwareStatusNotification": {},
            "Heartbeat": {},
            "MeterValues": {"connectorId": 1},
        }

        results = {}

        # Loop through each message type
        for message_type, params in triggered_messages.items():
            self._check_cancellation()
            logger.info(f"--- Triggering {message_type} ---")

            # Step 1: Create event to wait for the triggered message
            message_event = asyncio.Event()
            self.pending_triggered_message_events[message_type] = message_event

            try:
                # Step 2: Send TriggerMessage request
                payload = TriggerMessageRequest(requestedMessage=message_type, **params)
                trigger_response = await self.handler.send_and_wait(
                    "TriggerMessage",
                    payload,
                    timeout=15
                )
                self._check_cancellation()

                # Step 3: Check if trigger was accepted
                if not trigger_response or trigger_response.get("status") != "Accepted":
                    status = trigger_response.get("status", "NO_RESPONSE") if trigger_response else "NO_RESPONSE"
                    logger.error(f"FAILURE: TriggerMessage for {message_type} not accepted. Status: {status}")
                    results[message_type] = "FAILED"
                    continue

                logger.info(f"✓ TriggerMessage for {message_type} accepted. Waiting for the message...")

                # Step 4: Wait for the actual message to arrive
                try:
                    await asyncio.wait_for(message_event.wait(), timeout=10)
                    self._check_cancellation()
                    logger.info(f"SUCCESS: Received triggered {message_type} from charge point")
                    results[message_type] = "PASSED"
                except asyncio.TimeoutError:
                    logger.error(f"FAILURE: Timeout waiting for triggered {message_type}")
                    results[message_type] = "FAILED"

            finally:
                # Clean up the event
                self.pending_triggered_message_events.pop(message_type, None)

        # Summary
        logger.info("--- Test Summary ---")
        for message_type, result in results.items():
            if result == "PASSED":
                logger.info(f"  \033[92m{message_type}: {result}\033[0m")
            else:
                logger.error(f"  \033[91m{message_type}: {result}\033[0m")
        logger.info("--------------------")

        # Only pass if the three essential runtime messages pass
        essential_messages = ["Heartbeat", "MeterValues", "StatusNotification"]
        if all(results.get(msg) == "PASSED" for msg in essential_messages):
            logger.info(f"✅ All essential runtime messages (Heartbeat, MeterValues, StatusNotification) passed")
            self._set_test_result(step_name, "PASSED")
        else:
            failed_essential = [msg for msg in essential_messages if results.get(msg) != "PASSED"]
            logger.error(f"❌ Essential runtime messages failed: {', '.join(failed_essential)}")
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
            timeout=OCPP_MESSAGE_TIMEOUT
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
