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
                timeout=120  # Extended timeout for wallboxes that need initialization time
            )

            if response and response.get("configurationKey"):
                config_keys = response["configurationKey"]
                logger.info(f"    [OK] Received {len(config_keys)} configuration keys")
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
                    logger.warning(f"    [WARN]  {len(unknown_keys)} keys marked as unknown")

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
                logger.error("    [FAIL] No configuration keys received from charge point")
                logger.error("    ℹ️  Charge point may not support empty key array request")
                self._set_test_result(step_name, "FAILED")

        except Exception as e:
            logger.error(f"    [FAIL] Error requesting configuration: {e}")
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
                            logger.info(f"    [OK] {key}: {display_value}" + (" (RO)" if readonly else ""))
                            return (key, result_value)
                        else:
                            result_value = "No value" + (" (RO)" if readonly else "")
                            logger.info(f"    [WARN]  {key}: No value" + (" (RO)" if readonly else ""))
                            return (key, result_value)

                    elif response.get("unknownKey"):
                        logger.info(f"    [FAIL] {key}: Not Supported")
                        return (key, "N/A (Not Supported)")
                    else:
                        logger.info(f"    [FAIL] {key}: N/A")
                        return (key, "N/A")
                else:
                    logger.warning(f"    ⏱️  {key}: No response")
                    return (key, "NO_RESPONSE")

            except Exception as e:
                logger.error(f"    [FAIL] {key}: Error - {e}")
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
                logger.info(f"    [FAIL] {key}: N/A")
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
                logger.info(f"  [FAIL] {key}: {result}")
            elif "(RO)" in result:
                logger.info(f"  🔒 {key}: {result}")
            else:
                logger.info(f"  [OK] {key}: {result}")

        logger.info("\nOptional Profile Parameters:")
        optional_keys = ocpp_standard_keys[23:]  # Rest are optional
        for key in optional_keys:
            result = results.get(key, "UNKNOWN")
            if "N/A" in result or "NO_RESPONSE" in result:
                logger.info(f"  [WARN] {key}: {result}")
            elif "(RO)" in result:
                logger.info(f"  🔒 {key}: {result}")
            else:
                logger.info(f"  [OK] {key}: {result}")

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

        # Check if RemoteTrigger is supported (only if features were fetched by A.2)
        supported_features = CHARGE_POINTS.get(self.charge_point_id, {}).get("features", [])
        if supported_features and "RemoteTrigger" not in supported_features:
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
            logger.info(f"[OK] All essential runtime messages (Heartbeat, MeterValues, StatusNotification) passed")
            self._set_test_result(step_name, "PASSED")
        else:
            failed_essential = [msg for msg in essential_messages if results.get(msg) != "PASSED"]
            logger.error(f"[FAIL] Essential runtime messages failed: {', '.join(failed_essential)}")
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
        """A.6: Emulates EVCC reboot behavior - tests wallbox response to Central System restart."""
        logger.info(f"--- Step A.6: Emulating EVCC reboot for {self.charge_point_id} ---")
        step_name = "run_a6_evcc_reboot_behavior"
        self._check_cancellation()

        all_success = True
        results = {}

        from app.messages import ChangeConfigurationRequest

        # Set EV simulator to state A if available (optional, helps ensure clean state)
        if SERVER_SETTINGS.get("ev_simulator_available"):
            logger.info("Setting EV simulator to state A (disconnected)...")
            try:
                await self._set_ev_state("A")
            except Exception as e:
                logger.debug(f"Could not set EV state (non-critical): {e}")

        logger.info("=" * 80)
        logger.info("EVCC REBOOT EMULATION TEST")
        logger.info("=" * 80)
        logger.info("This test emulates Central System restart to verify wallbox behavior:")
        logger.info("  Phase 1: Close WebSocket connection and verify disconnection")
        logger.info("  Phase 2: Block reconnections for 10 seconds (simulate EVCC offline)")
        logger.info("  Phase 3: Allow reconnections - wallbox reconnects automatically")
        logger.info("  Phase 4: Verify BootNotification → StatusNotification sequence")
        logger.info("  Phase 5: Send Central System configuration commands (matches EVCC)")
        logger.info("=" * 80)
        logger.info("")

        # Phase 1: Stop OCPP server (emulating EVCC shutdown - port 8888 closed)
        logger.info("Phase 1: Stopping OCPP server (emulating EVCC shutdown)...")
        from app.core import stop_ocpp_server, start_ocpp_server

        # Clear BootNotification data so we can verify if wallbox sends it again after reconnection
        if self.charge_point_id in CHARGE_POINTS:
            cp_info = CHARGE_POINTS[self.charge_point_id]
            # Save the old values for logging
            old_model = cp_info.get("model")
            old_vendor = cp_info.get("vendor")
            # Clear them to detect new BootNotification
            cp_info.pop("model", None)
            cp_info.pop("vendor", None)
            logger.info(f"  Cleared BootNotification data (was: {old_vendor} {old_model})")

        # Stop the server (closes port 8888 - like EVCC not running)
        stop_success = await stop_ocpp_server()
        if not stop_success:
            logger.error("  [FAIL] Failed to stop OCPP server")
            results["Server Stopped"] = "FAILED"
            all_success = False
            self._set_test_result(step_name, "FAILED", "Failed to stop OCPP server")
            logger.info(f"--- Step A.6 for {self.charge_point_id} complete. ---")
            return

        logger.info("  [OK] OCPP server stopped - port 8888 closed (wallbox cannot connect)")
        results["Server Stopped"] = "PASSED"

        # Phase 2: EVCC offline period (simulates EVCC startup time)
        logger.info("Phase 2: EVCC offline period (port 8888 not listening, wallbox cannot connect)...")
        offline_period = 10  # seconds (matches typical EVCC startup time from spec)
        logger.info(f"  Port 8888 closed for {offline_period}s (simulating EVCC startup)")
        await asyncio.sleep(offline_period)

        # Restart the server (opens port 8888 - like EVCC finished starting)
        logger.info("  Restarting OCPP server (EVCC back online)...")
        start_success = await start_ocpp_server()
        if not start_success:
            logger.error("  [FAIL] Failed to restart OCPP server")
            results["Server Restarted"] = "FAILED"
            all_success = False
            self._set_test_result(step_name, "FAILED", "Failed to restart OCPP server")
            logger.info(f"--- Step A.6 for {self.charge_point_id} complete. ---")
            return

        logger.info("  [OK] OCPP server restarted - port 8888 listening again")
        results["Server Restarted"] = "PASSED"

        # Phase 3: Wait for wallbox reconnection
        logger.info("Phase 3: Waiting for wallbox to reconnect...")
        reconnected = False
        reconnect_timeout = 120  # seconds - allow for wallboxes with long ConnectionTimeOut (e.g., 90s) + retry backoff
        check_interval = 1  # second
        elapsed = 0

        while not reconnected and elapsed < reconnect_timeout:
            await asyncio.sleep(check_interval)
            self._check_cancellation()
            elapsed += check_interval

            # Check if wallbox has reconnected (check if entry exists with a handler)
            if self.charge_point_id in CHARGE_POINTS:
                handler = CHARGE_POINTS[self.charge_point_id].get("ocpp_handler")
                if handler is not None and handler != self.handler:
                    logger.info(f"  [OK] Wallbox reconnected after {elapsed}s from unblock ({elapsed + offline_period}s total)")

                    # Transfer message logging wrappers from old handler to new handler
                    # This is critical for A.6 test logging - the server restart creates a new handler
                    # but we need to preserve message logging for the test log file
                    old_handler = self.handler
                    if hasattr(old_handler, '_test_log_message'):
                        logger.debug("  [OK] Recreating message logging wrappers for new handler")
                        from datetime import datetime
                        import uuid

                        # Get the log_message function from old handler
                        log_message_func = old_handler._test_log_message

                        # Store new handler's original send_and_wait
                        new_original_send_and_wait = handler.send_and_wait

                        # Create a NEW wrapper for the new handler (can't reuse old wrapper - it has old handler's closure)
                        async def new_wrapped_send_and_wait(action: str, payload, timeout: int = OCPP_MESSAGE_TIMEOUT):
                            """Wrapper to log all OCPP requests and responses for the new handler."""
                            message_id = str(uuid.uuid4())
                            request_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                            log_message_func("REQUEST", action, payload, request_timestamp, message_id, test_name="run_a6_evcc_reboot_behavior")

                            response = await new_original_send_and_wait(action, payload, timeout)

                            response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                            if response is None:
                                log_message_func("RESPONSE_TIMEOUT", action, {"error": f"Timeout after {timeout}s - no response received from charge point"}, response_timestamp, message_id, test_name="run_a6_evcc_reboot_behavior")
                            else:
                                log_message_func("RESPONSE", action, response, response_timestamp, message_id, test_name="run_a6_evcc_reboot_behavior")

                            return response

                        # Apply wrappers to new handler
                        handler.send_and_wait = new_wrapped_send_and_wait
                        handler.incoming_message_logger = log_message_func
                        handler._test_log_message = log_message_func
                        handler._test_wrapped_send_and_wait = new_wrapped_send_and_wait
                        handler._original_send_and_wait = new_original_send_and_wait

                    # Update to the new handler
                    self.handler = handler
                    logger.info("  [OK] Handler updated to new connection")
                    results["Wallbox Reconnected"] = "PASSED"
                    reconnected = True
                    break

            if elapsed % 10 == 0:
                logger.info(f"  ⏳ Still waiting... ({elapsed}/{reconnect_timeout}s)")

        if not reconnected:
            logger.error(f"  [FAIL] Wallbox did not reconnect within {reconnect_timeout} seconds")
            results["Wallbox Reconnected"] = "FAILED"
            all_success = False
            self._set_test_result(step_name, "FAILED", "Wallbox failed to reconnect")
            logger.info(f"--- Step A.6 for {self.charge_point_id} complete. ---")
            return

        # Phase 4: Verify message sequence (BootNotification and StatusNotification already received during reconnection)
        logger.info("Phase 4: Verifying OCPP message sequence...")

        # Check if BootNotification was received (wallbox info should be present)
        if self.charge_point_id in CHARGE_POINTS:
            cp_info = CHARGE_POINTS[self.charge_point_id]
            if cp_info.get("model") and cp_info.get("vendor"):
                logger.info("  [OK] BootNotification received and processed")
                results["BootNotification Received"] = "PASSED"
            else:
                logger.warning("  [WARN] BootNotification NOT received after reconnection (OCPP spec violation)")
                logger.warning("  [WARN] Per OCPP 1.6 spec: BootNotification MUST be first message after connection")
                logger.warning("  [WARN] This is a wallbox compliance issue but test will continue")
                results["BootNotification Received"] = "WARNING (OCPP Violation)"
                # Don't fail the test, just note the violation

            # Check if StatusNotification was received
            if cp_info.get("status"):
                logger.info(f"  [OK] StatusNotification received (status: {cp_info.get('status')})")
                results["StatusNotification Received"] = "PASSED"
            else:
                logger.error("  [FAIL] StatusNotification not confirmed (missing status)")
                results["StatusNotification Received"] = "FAILED"
                all_success = False

        # Phase 5: Send EVCC configuration commands
        logger.info("Phase 5: Sending EVCC configuration commands...")

        # Use longer timeout after reconnection - wallbox may be slower to respond
        post_reconnect_timeout = 60  # seconds

        # 5.0: ChangeAvailability (Optional - EVCC sends this)
        logger.info("  5.0 - Sending ChangeAvailability (Operative)...")
        from app.messages import ChangeAvailabilityRequest
        try:
            avail_response = await self.handler.send_and_wait(
                "ChangeAvailability",
                ChangeAvailabilityRequest(connectorId=0, type="Operative"),
                timeout=post_reconnect_timeout
            )
            if avail_response and avail_response.get("status") in ["Accepted", "Scheduled"]:
                logger.info(f"    [OK] ChangeAvailability: {avail_response.get('status')}")
                results["ChangeAvailability"] = "PASSED"
            else:
                status = avail_response.get("status") if avail_response else "NO_RESPONSE"
                logger.warning(f"    [WARN]  ChangeAvailability: {status} (optional command)")
                results["ChangeAvailability"] = "WARNING"
        except Exception as e:
            logger.warning(f"    [WARN]  ChangeAvailability error: {e} (optional command)")
            results["ChangeAvailability"] = "WARNING"

        # 5.1: GetConfiguration (using empty payload {} to match EVCC exactly)
        logger.info("  5.1 - Sending GetConfiguration...")
        try:
            config_response = await self.handler.send_and_wait(
                "GetConfiguration",
                GetConfigurationRequest(),  # Empty payload {} (same as EVCC)
                timeout=post_reconnect_timeout
            )
            if config_response and config_response.get("configurationKey"):
                logger.info(f"    [OK] GetConfiguration: Received {len(config_response['configurationKey'])} keys")
                results["GetConfiguration"] = "PASSED"
            else:
                logger.error("    [FAIL] GetConfiguration: No response or empty")
                results["GetConfiguration"] = "FAILED"
                all_success = False
        except Exception as e:
            logger.error(f"    [FAIL] GetConfiguration error: {e}")
            results["GetConfiguration"] = "FAILED"
            all_success = False

        # 5.2: ChangeConfiguration for MeterValuesSampledData
        logger.info("  5.2 - Sending ChangeConfiguration (MeterValuesSampledData)...")
        try:
            meter_values_config = "Power.Active.Import,Energy.Active.Import.Register,Current.Import,Voltage,Current.Offered,Power.Offered,SoC"
            change_response = await self.handler.send_and_wait(
                "ChangeConfiguration",
                ChangeConfigurationRequest(key="MeterValuesSampledData", value=meter_values_config),
                timeout=post_reconnect_timeout
            )
            if change_response and change_response.get("status") in ["Accepted", "RebootRequired"]:
                logger.info(f"    [OK] ChangeConfiguration (MeterValuesSampledData): {change_response.get('status')}")
                results["ChangeConfiguration MeterValuesSampledData"] = "PASSED"
            else:
                status = change_response.get("status") if change_response else "NO_RESPONSE"
                logger.error(f"    [FAIL] ChangeConfiguration (MeterValuesSampledData): {status}")
                results["ChangeConfiguration MeterValuesSampledData"] = "FAILED"
                all_success = False
        except Exception as e:
            logger.error(f"    [FAIL] ChangeConfiguration error: {e}")
            results["ChangeConfiguration MeterValuesSampledData"] = "FAILED"
            all_success = False

        # 5.3: ChangeConfiguration for MeterValueSampleInterval
        logger.info("  5.3 - Sending ChangeConfiguration (MeterValueSampleInterval)...")
        try:
            change_response = await self.handler.send_and_wait(
                "ChangeConfiguration",
                ChangeConfigurationRequest(key="MeterValueSampleInterval", value="10"),
                timeout=post_reconnect_timeout
            )
            if change_response and change_response.get("status") in ["Accepted", "RebootRequired"]:
                logger.info(f"    [OK] ChangeConfiguration (MeterValueSampleInterval): {change_response.get('status')}")
                results["ChangeConfiguration MeterValueSampleInterval"] = "PASSED"
            else:
                status = change_response.get("status") if change_response else "NO_RESPONSE"
                logger.error(f"    [FAIL] ChangeConfiguration (MeterValueSampleInterval): {status}")
                results["ChangeConfiguration MeterValueSampleInterval"] = "FAILED"
                all_success = False
        except Exception as e:
            logger.error(f"    [FAIL] ChangeConfiguration error: {e}")
            results["ChangeConfiguration MeterValueSampleInterval"] = "FAILED"
            all_success = False

        # 5.4: ChangeConfiguration for WebSocketPingInterval
        logger.info("  5.4 - Sending ChangeConfiguration (WebSocketPingInterval)...")
        try:
            change_response = await self.handler.send_and_wait(
                "ChangeConfiguration",
                ChangeConfigurationRequest(key="WebSocketPingInterval", value="30"),
                timeout=post_reconnect_timeout
            )
            if change_response and change_response.get("status") in ["Accepted", "RebootRequired"]:
                logger.info(f"    [OK] ChangeConfiguration (WebSocketPingInterval): {change_response.get('status')}")
                results["ChangeConfiguration WebSocketPingInterval"] = "PASSED"
            else:
                status = change_response.get("status") if change_response else "NO_RESPONSE"
                logger.error(f"    [FAIL] ChangeConfiguration (WebSocketPingInterval): {status}")
                results["ChangeConfiguration WebSocketPingInterval"] = "FAILED"
                all_success = False
        except Exception as e:
            logger.error(f"    [FAIL] ChangeConfiguration error: {e}")
            results["ChangeConfiguration WebSocketPingInterval"] = "FAILED"
            all_success = False

        # 5.5: TriggerMessage for BootNotification
        logger.info("  5.5 - Sending TriggerMessage (BootNotification)...")
        try:
            trigger_response = await self.handler.send_and_wait(
                "TriggerMessage",
                TriggerMessageRequest(requestedMessage="BootNotification"),
                timeout=post_reconnect_timeout
            )
            if trigger_response and trigger_response.get("status") == "Accepted":
                logger.info("    [OK] TriggerMessage (BootNotification): Accepted")
                results["TriggerMessage BootNotification"] = "PASSED"
            else:
                status = trigger_response.get("status") if trigger_response else "NO_RESPONSE"
                logger.error(f"    [FAIL] TriggerMessage (BootNotification): {status}")
                results["TriggerMessage BootNotification"] = "FAILED"
                all_success = False
        except Exception as e:
            logger.error(f"    [FAIL] TriggerMessage error: {e}")
            results["TriggerMessage BootNotification"] = "FAILED"
            all_success = False

        # 5.6: TriggerMessage for MeterValues
        logger.info("  5.6 - Sending TriggerMessage (MeterValues)...")
        try:
            trigger_response = await self.handler.send_and_wait(
                "TriggerMessage",
                TriggerMessageRequest(requestedMessage="MeterValues", connectorId=1),
                timeout=post_reconnect_timeout
            )
            if trigger_response and trigger_response.get("status") == "Accepted":
                logger.info("    [OK] TriggerMessage (MeterValues): Accepted")
                results["TriggerMessage MeterValues"] = "PASSED"
            else:
                status = trigger_response.get("status") if trigger_response else "NO_RESPONSE"
                logger.error(f"    [FAIL] TriggerMessage (MeterValues): {status}")
                results["TriggerMessage MeterValues"] = "FAILED"
                all_success = False
        except Exception as e:
            logger.error(f"    [FAIL] TriggerMessage error: {e}")
            results["TriggerMessage MeterValues"] = "FAILED"
            all_success = False

        # Summary
        logger.info("")
        logger.info("=" * 80)
        logger.info("EVCC REBOOT EMULATION TEST - Summary")
        logger.info("=" * 80)
        for key, result in results.items():
            if result == "PASSED":
                logger.info(f"  [OK] {key}: {result}")
            elif "WARNING" in result:
                logger.warning(f"  [WARN] {key}: {result}")
            else:
                logger.error(f"  [FAIL] {key}: {result}")
        logger.info("=" * 80)

        if all_success:
            self._set_test_result(step_name, "PASSED")
            logger.info("[OK] Test PASSED: Wallbox correctly handles EVCC reboot")
        else:
            self._set_test_result(step_name, "FAILED")
            logger.error("[FAIL] Test FAILED: Check results above for details")

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
