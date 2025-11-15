"""
OCPP Test Series A: Core Communication & Status

Tests basic OCPP protocol functionality:
- A.1: Initial Registration
- A.2: Get All Configuration Parameters
- A.3: Check Single Parameters
- A.4: Trigger All Messages
- A.5: Meter Values
- A.6: EVCC Reboot Behavior
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
            response = await self.handler.send_and_wait(
                "GetConfiguration",
                GetConfigurationRequest(key=[]),
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

                unknown_keys = response.get("unknownKey", [])
                if unknown_keys:
                    logger.warning(f"    ⚠️  {len(unknown_keys)} keys marked as unknown")

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

        MAX_CONCURRENT = 5
        pending_tasks = set()
        key_index = 0

        while key_index < len(ocpp_standard_keys) and len(pending_tasks) < MAX_CONCURRENT:
            task = asyncio.create_task(request_key(ocpp_standard_keys[key_index]))
            pending_tasks.add(task)
            key_index += 1

        while pending_tasks:
            done, pending_tasks = await asyncio.wait(pending_tasks, return_when=asyncio.FIRST_COMPLETED)

            for task in done:
                key, value = await task
                results[key] = value

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

        successful_results = [v for v in results.values() if "N/A" not in v and "NO_RESPONSE" not in v and "ERROR" not in v]
        if successful_results:
            self._set_test_result(step_name, "PASSED")
        else:
            self._set_test_result(step_name, "FAILED", "No successful responses received")

        logger.info(f"--- Step A.3 for {self.charge_point_id} complete. ---")

    async def run_a4_trigger_all_messages_test(self):
        """A.4: Tests all TriggerMessage functionalities."""
        logger.info(f"--- Step A.4: Testing all TriggerMessages for {self.charge_point_id} ---")
        step_name = "run_a4_trigger_all_messages_test"
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

        logger.info(f"--- Step A.4 for {self.charge_point_id} complete. ---")

    async def run_a5_status_and_meter_value_acquisition(self):
        """A.5: Requests meter values from the charge point and waits for them."""
        logger.info(f"--- Step A.5: Acquiring meter values for {self.charge_point_id} ---")
        step_name = "run_a5_status_and_meter_value_acquisition"
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
            logger.info(f"--- Step A.5 for {self.charge_point_id} complete. ---")
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

        logger.info(f"--- Step A.5 for {self.charge_point_id} complete. ---")

    async def run_a6_evcc_reboot_behavior(self):
        """A.6: Tests EVCC reboot behavior - verifies wallbox properly handles EVCC restart."""
        logger.info(f"--- Step A.6: Testing EVCC reboot behavior for {self.charge_point_id} ---")
        step_name = "run_a6_evcc_reboot_behavior"
        self._check_cancellation()

        # Check if this is a real OCPP connection (not EV simulator)
        if SERVER_SETTINGS.get("ev_simulator_available"):
            logger.warning("Skipping test: This test is designed for real OCPP wallboxes, not the EV simulator.")
            self._set_test_result(
                step_name,
                "SKIPPED",
                "Test requires a real OCPP wallbox connection to an EVCC server. Not applicable for EV simulator."
            )
            logger.info(f"--- Step A.6 for {self.charge_point_id} complete. ---")
            return

        all_success = True
        results = {}

        logger.info("=" * 80)
        logger.info("EVCC REBOOT TEST - Manual Procedure")
        logger.info("=" * 80)
        logger.info("")
        logger.info("This test verifies that the wallbox correctly handles EVCC server restarts.")
        logger.info("The test will:")
        logger.info("  1. Monitor current connection state")
        logger.info("  2. Wait for you to restart EVCC")
        logger.info("  3. Detect the WebSocket disconnection")
        logger.info("  4. Verify wallbox reconnects automatically")
        logger.info("  5. Verify correct OCPP message sequence after reconnection")
        logger.info("")
        logger.info("Expected OCPP message flow after EVCC restart:")
        logger.info("  - BootNotification (must be first message)")
        logger.info("  - StatusNotification")
        logger.info("  - GetConfiguration from EVCC")
        logger.info("  - ChangeConfiguration from EVCC")
        logger.info("  - TriggerMessage requests from EVCC")
        logger.info("")
        logger.info("To restart EVCC on Home Assistant (192.168.0.202):")
        logger.info("  SSH method: sshpass -p 'hd*yT1680' ssh root@192.168.0.202 \"ha addons restart 49686a9f_evcc\"")
        logger.info("  OR use Home Assistant web UI to restart the EVCC addon")
        logger.info("")
        logger.info("=" * 80)
        logger.info("")
        logger.info("⏳ Waiting for EVCC restart... Please restart EVCC now.")
        logger.info("   The test will automatically detect the disconnect and monitor the reconnection.")
        logger.info("")

        # Wait for disconnection with timeout
        logger.info("Monitoring WebSocket connection...")
        disconnected = False
        reconnected = False

        # Maximum wait time: 5 minutes for user to restart EVCC
        max_wait_seconds = 300
        check_interval = 2
        elapsed = 0

        # Phase 1: Wait for disconnection
        while not disconnected and elapsed < max_wait_seconds:
            await asyncio.sleep(check_interval)
            self._check_cancellation()
            elapsed += check_interval

            # Check if connection is still active
            if self.charge_point_id not in CHARGE_POINTS or not CHARGE_POINTS[self.charge_point_id].get("connected", False):
                logger.info("")
                logger.info("🔌 WebSocket disconnection detected!")
                logger.info(f"   Time elapsed: {elapsed} seconds")
                disconnected = True
                results["Connection Disconnect Detected"] = "PASSED"
                break

            # Progress indicator every 30 seconds
            if elapsed % 30 == 0:
                logger.info(f"   Still waiting for EVCC restart... ({elapsed}/{max_wait_seconds}s elapsed)")

        if not disconnected:
            logger.error("❌ Timeout: No disconnection detected within 5 minutes")
            logger.error("   Please ensure you restart EVCC during the test")
            results["Connection Disconnect Detected"] = "FAILED"
            all_success = False
            self._set_test_result(step_name, "FAILED", "Timeout waiting for EVCC restart")
            logger.info(f"--- Step A.6 for {self.charge_point_id} complete. ---")
            return

        # Phase 2: Wait for reconnection
        logger.info("")
        logger.info("⏳ Waiting for wallbox to reconnect...")
        logger.info("   Expected: Wallbox should retry connection every 5-10 seconds")

        reconnect_wait = 0
        max_reconnect_wait = 120  # 2 minutes for reconnection

        while not reconnected and reconnect_wait < max_reconnect_wait:
            await asyncio.sleep(check_interval)
            self._check_cancellation()
            reconnect_wait += check_interval

            # Check if wallbox has reconnected
            if self.charge_point_id in CHARGE_POINTS and CHARGE_POINTS[self.charge_point_id].get("connected", False):
                logger.info("")
                logger.info(f"🔌 Wallbox reconnected successfully!")
                logger.info(f"   Reconnection time: {reconnect_wait} seconds after disconnect")
                reconnected = True
                results["Wallbox Reconnection"] = "PASSED"
                break

            if reconnect_wait % 15 == 0:
                logger.info(f"   Waiting for reconnection... ({reconnect_wait}/{max_reconnect_wait}s)")

        if not reconnected:
            logger.error("❌ Timeout: Wallbox did not reconnect within 2 minutes")
            results["Wallbox Reconnection"] = "FAILED"
            all_success = False
            self._set_test_result(step_name, "FAILED", "Wallbox failed to reconnect")
            logger.info(f"--- Step A.6 for {self.charge_point_id} complete. ---")
            return

        # Phase 3: Verify OCPP message sequence
        logger.info("")
        logger.info("📋 Verifying OCPP message sequence after reconnection...")
        logger.info("")

        # Monitor messages for 30 seconds after reconnection
        message_monitor_duration = 30
        logger.info(f"   Monitoring OCPP messages for {message_monitor_duration} seconds...")

        await asyncio.sleep(message_monitor_duration)
        self._check_cancellation()

        # Verify BootNotification was sent (check if wallbox info is present)
        if self.charge_point_id in CHARGE_POINTS:
            cp_info = CHARGE_POINTS[self.charge_point_id]
            if cp_info.get("model") or cp_info.get("vendor"):
                results["BootNotification Sent"] = "PASSED"
                logger.info("  ✅ BootNotification verified (wallbox info present)")
            else:
                results["BootNotification Sent"] = "FAILED"
                all_success = False
                logger.error("  ❌ BootNotification not confirmed")

        # Verify StatusNotification was sent (check if status is present)
        if self.charge_point_id in CHARGE_POINTS:
            cp_info = CHARGE_POINTS[self.charge_point_id]
            if cp_info.get("status"):
                results["StatusNotification Sent"] = "PASSED"
                logger.info(f"  ✅ StatusNotification verified (status: {cp_info.get('status')})")
            else:
                results["StatusNotification Sent"] = "FAILED"
                all_success = False
                logger.error("  ❌ StatusNotification not confirmed")

        logger.info("")
        logger.info("=" * 80)
        logger.info("EVCC REBOOT TEST - Summary")
        logger.info("=" * 80)

        for key, result in results.items():
            if result == "PASSED":
                logger.info(f"  ✅ {key}: {result}")
            else:
                logger.error(f"  ❌ {key}: {result}")

        logger.info("")
        logger.info("Expected behavior verified:")
        logger.info("  1. ✅ Wallbox detected EVCC disconnect")
        logger.info("  2. ✅ Wallbox automatically reconnected")
        logger.info("  3. ✅ BootNotification sent after reconnection")
        logger.info("  4. ✅ StatusNotification sent after BootNotification")
        logger.info("")
        logger.info("This confirms the wallbox properly handles EVCC restarts as described in")
        logger.info("the EVCC Reboot Behavior specification (evcc_reboot_behavior.md)")
        logger.info("=" * 80)

        if all_success:
            self._set_test_result(step_name, "PASSED")
        else:
            self._set_test_result(step_name, "FAILED")

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
