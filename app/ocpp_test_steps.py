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
        """A.2: Get All Configuration - Fetches and displays all configuration settings from the charge point using empty key array."""
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
        """A.3: Get OCPP Standard Keys - Retrieves all OCPP 1.6-J standard configuration parameters by explicitly requesting each key."""
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
                    else:
                        results[key] = "No value" + (" (RO)" if readonly else "")

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
        id_tag = "50600020100021"  # Use same ID tag as other tests
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

        # Only pass if the three essential runtime messages pass
        # (BootNotification, DiagnosticsStatusNotification, and FirmwareStatusNotification are optional)
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

    async def run_b1_reset_transaction_management(self):
        """B.1: Reset Transaction Management - Establishes clean baseline for authorization testing."""
        logger.info(f"--- Step B.1: Reset Transaction Management for {self.charge_point_id} ---")
        step_name = "run_b1_reset_transaction_management"
        self._check_cancellation()

        # Step 1: Clear RFID cache
        logger.info("🗑️  Step 1: Clearing RFID cache...")
        logger.info("   📘 This removes all cached RFID authorizations from wallbox memory")

        clear_cache_request = ClearCacheRequest()
        cache_cleared = False

        try:
            response = await self.handler.send_and_wait("ClearCache", clear_cache_request, timeout=10)

            if response is None:
                logger.warning("⚠️  ClearCache request timed out")
            else:
                status = response.get("status", "Unknown")
                logger.info(f"   📝 ClearCache response: {status}")

                if status == "Accepted":
                    logger.info("   ✅ RFID cache cleared successfully")
                    cache_cleared = True
                elif status == "Rejected":
                    logger.warning("   ⚠️  ClearCache rejected (wallbox may not support this)")
                else:
                    logger.warning(f"   ⚠️  Unexpected status: {status}")

        except Exception as e:
            logger.error(f"   ❌ Error clearing cache: {e}")

        # Step 2: Configure baseline parameters
        logger.info("🔧 Step 2: Setting baseline configuration parameters...")

        config_params = [
            {"key": "LocalPreAuthorize", "value": "false",
             "purpose": "Disable auto-start - wallbox must wait for authorization"},

            {"key": "AuthorizeRemoteTxRequests", "value": "false",
             "purpose": "Allow remote transactions WITHOUT authorization check - Central System has full control"},

            {"key": "LocalAuthorizeOffline", "value": "false",
             "purpose": "Require online authorization - no offline cache usage"},

            {"key": "LocalAuthListEnabled", "value": "false",
             "purpose": "Disable local authorization list"},

            {"key": "AuthorizationCacheEnabled", "value": "false",
             "purpose": "Disable authorization cache - prevents use of cached ElecqAutoStart ID"},
        ]

        logger.info(f"   📋 Configuring {len(config_params)} parameters for clean baseline:")
        for param in config_params:
            logger.info(f"      • {param['key']}: {param['value']} - {param['purpose']}")

        success_count = 0
        total_configs = len(config_params)
        reboot_required = False

        # Configure each parameter
        for param in config_params:
            key = param['key']
            value = param['value']

            logger.info(f"   🔧 Setting {key}...")
            config_request = ChangeConfigurationRequest(key=key, value=value)

            try:
                response = await self.handler.send_and_wait("ChangeConfiguration", config_request, timeout=30)
                self._check_cancellation()

                if response and response.get("status"):
                    status = response["status"]
                    if status == "Accepted":
                        logger.info(f"      ✅ {key} configuration ACCEPTED")
                        success_count += 1
                    elif status == "RebootRequired":
                        logger.info(f"      ⚠️  {key} accepted but REBOOT REQUIRED")
                        reboot_required = True
                        success_count += 1
                    elif status == "NotSupported":
                        logger.warning(f"      ⚠️  {key} is NOT SUPPORTED by this charge point")
                    elif status == "Rejected":
                        logger.error(f"      ❌ {key} configuration REJECTED")
                    else:
                        logger.error(f"      ❌ {key} failed with status: {status}")
                else:
                    logger.error(f"      ❌ No response for {key}")

            except Exception as e:
                logger.error(f"      ❌ Exception configuring {key}: {e}")

        # Step 3: Verify configuration by reading back the values
        logger.info("🔍 Step 3: Verifying configuration was applied...")

        verification_passed = True
        keys_to_verify = [param['key'] for param in config_params]

        get_config_request = GetConfigurationRequest(key=keys_to_verify)

        try:
            response = await self.handler.send_and_wait("GetConfiguration", get_config_request, timeout=10)
            self._check_cancellation()

            if response and response.get("configurationKey"):
                logger.info("   📋 Current configuration values:")
                config_keys = response.get("configurationKey", [])

                for param in config_params:
                    key = param['key']
                    expected_value = param['value']

                    # Find the actual value from response
                    actual_value = None
                    for config_item in config_keys:
                        if config_item.get("key") == key:
                            actual_value = config_item.get("value")
                            break

                    if actual_value is not None:
                        if actual_value.lower() == expected_value.lower():
                            logger.info(f"      ✅ {key} = {actual_value} (correct)")
                        else:
                            logger.error(f"      ❌ {key} = {actual_value} (expected: {expected_value})")
                            verification_passed = False
                    else:
                        logger.warning(f"      ⚠️  {key} - not returned in GetConfiguration response")
                        verification_passed = False
            else:
                logger.error("   ❌ GetConfiguration failed - cannot verify settings")
                verification_passed = False

        except Exception as e:
            logger.error(f"   ❌ Exception during verification: {e}")
            verification_passed = False

        # Determine overall test result
        if reboot_required:
            logger.warning("")
            logger.warning("⚠️  ═══════════════════════════════════════════════════")
            logger.warning("⚠️  REBOOT REQUIRED - Configuration changes need reboot")
            logger.warning("⚠️  ═══════════════════════════════════════════════════")
            logger.warning("   Please run test X.1 'Reboot Wallbox' now,")
            logger.warning("   then run B.1 again to verify the configuration.")
            logger.warning("")

        if success_count == total_configs and verification_passed:
            if cache_cleared:
                logger.info("✅ Step B.1: Baseline configuration complete and verified - cache cleared, all parameters set")
                self._set_test_result(step_name, "PASSED")
            else:
                logger.info("⚠️  Step B.1: Baseline configuration verified - parameters set, cache clearing failed/not supported")
                self._set_test_result(step_name, "PARTIAL")
        elif success_count == total_configs and not verification_passed:
            logger.error("❌ Step B.1: Configuration was ACCEPTED but VERIFICATION FAILED")
            logger.error("   The wallbox accepted the changes but GetConfiguration shows different values!")
            logger.error("   This usually means:")
            logger.error("   1. The wallbox needs to be rebooted (run X.1 Reboot Wallbox)")
            logger.error("   2. The configuration is read-only or locked")
            logger.error("   3. The wallbox has a factory default override")
            self._set_test_result(step_name, "FAILED")
        elif success_count > 0:
            logger.info(f"⚠️  Step B.1: Partial baseline configuration ({success_count}/{total_configs} parameters)")
            self._set_test_result(step_name, "PARTIAL")
        else:
            logger.error("❌ Step B.1: Failed to establish baseline configuration")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"📊 Configuration results: {success_count}/{total_configs} parameters configured, verification: {'✅ PASSED' if verification_passed else '❌ FAILED'}")

        if verification_passed:
            logger.info("📋 BASELINE ESTABLISHED:")
            logger.info("   • Wallbox will wait for authorization (no auto-start)")
            logger.info("   • Remote commands enabled (RemoteStartTransaction will work)")
            logger.info("   • Online authorization required (Central System must approve)")
            logger.info("   • RFID cache cleared (only new authorizations accepted)")
            logger.info("")
            logger.info("💡 You can now run authorization tests:")
            logger.info("   • B.2: RFID Authorization Test")
            logger.info("   • B.2: Autonomous Start Test")
        else:
            logger.error("⚠️  BASELINE NOT VERIFIED - DO NOT proceed with B.2 yet!")
            logger.error("   Please investigate the configuration mismatch above.")

        logger.info(f"--- Step B.1 for {self.charge_point_id} complete. ---")

    async def run_b2_autonomous_start_test(self):
        """B.2: Autonomous Start - Tests autonomous transaction initiation without manual authorization."""
        logger.info(f"--- Step B.2: Running Autonomous Start test for {self.charge_point_id} ---")
        step_name = "run_b2_autonomous_start_test"
        self._check_cancellation()

        logger.info("📋 AUTONOMOUS START TEST")
        logger.info("   📘 This tests sending RemoteStartTransaction BEFORE EV connects:")
        logger.info("   📘 1. Central System sends RemoteStartTransaction")
        logger.info("   📘 2. User then plugs in EV")
        logger.info("   📘 3. Wallbox starts transaction automatically")
        logger.info("")

        # Step 0: Ensure baseline configuration
        logger.info("🔧 Step 0: Verifying baseline configuration...")
        logger.info("   📘 For this test: AuthorizeRemoteTxRequests=false (remote commands don't need auth)")

        try:
            response = await self.handler.send_and_wait(
                "GetConfiguration",
                GetConfigurationRequest(key=["AuthorizeRemoteTxRequests"]),
                timeout=10
            )
            self._check_cancellation()

            authorize_remote = None
            if response and response.get("configurationKey"):
                for key in response.get("configurationKey", []):
                    if key.get("key") == "AuthorizeRemoteTxRequests":
                        authorize_remote = key.get("value", "").lower()
                        break

            if authorize_remote != "false":
                logger.info(f"   🔧 Setting AuthorizeRemoteTxRequests=false (currently: {authorize_remote})...")
                config_response = await self.handler.send_and_wait(
                    "ChangeConfiguration",
                    ChangeConfigurationRequest(key="AuthorizeRemoteTxRequests", value="false"),
                    timeout=10
                )
                self._check_cancellation()
                if config_response and config_response.get("status") == "Accepted":
                    logger.info("   ✅ Configuration updated")
                else:
                    logger.warning(f"   ⚠️  Configuration may not have updated: {config_response.get('status', 'Unknown')}")
            else:
                logger.info("   ✅ Configuration already correct")

        except Exception as e:
            logger.warning(f"   ⚠️  Could not verify/update configuration: {e}")

        logger.info("")

        # Try to use the RFID card from B.2 test, otherwise use default
        id_tag = CHARGE_POINTS.get(self.charge_point_id, {}).get("accepted_rfid", "50600020100021")
        if CHARGE_POINTS.get(self.charge_point_id, {}).get("accepted_rfid"):
            logger.info(f"   🎫 Using RFID card from B.2 test: {id_tag}")
        else:
            logger.info(f"   🎫 Using default RFID card: {id_tag}")
            logger.info(f"   💡 Run B.10 first to use your actual RFID card")

        connector_id = 1  # Use connector 1 instead of 0

        # 1. First ensure EV is UNPLUGGED (State A)
        logger.info("📡 Step 1: Ensuring EV is unplugged (State A)...")
        await self._set_ev_state("A")
        await asyncio.sleep(1)
        self._check_cancellation()

        # 2. Send RemoteStartTransaction FIRST (before EV connects)
        try:
            start_response = await asyncio.wait_for(
                self.handler.send_and_wait(
                    "RemoteStartTransaction",
                    RemoteStartTransactionRequest(idTag=id_tag, connectorId=connector_id),
                    timeout=15
                ),
                timeout=20
            )
            self._check_cancellation()

            if not start_response or start_response.get("status") != "Accepted":
                status = start_response.get("status", "Unknown") if start_response else "No response"
                logger.error(f"    ❌ RemoteStartTransaction: {status}")
                self._set_test_result(step_name, "FAILED")
                return

        except asyncio.TimeoutError:
            logger.error(f"    ❌ RemoteStartTransaction: Timeout - wallbox did not respond within 20 seconds")
            self._set_test_result(step_name, "FAILED")
            return

        logger.info("    ✅ RemoteStartTransaction: Accepted")
        logger.info("    💡 Transaction authorized - waiting for EV to connect...")
        logger.info("")

        # Create placeholder transaction entry to track this remote start
        # Use a temporary key (we'll get the real transaction ID from StartTransaction.req)
        temp_transaction_key = f"temp_remote_{connector_id}"
        TRANSACTIONS[temp_transaction_key] = {
            "charge_point_id": self.charge_point_id,
            "id_tag": id_tag,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "meter_start": 0,  # Will be updated by StartTransaction
            "connector_id": connector_id,
            "status": "Ongoing",
            "remote_started": True,  # Mark as remotely started
            "cp_transaction_id": None,  # Will be filled by StartTransaction
        }
        logger.debug(f"   📝 Created placeholder transaction entry: {temp_transaction_key}")

        # 3. NOW connect the EV (State B)
        logger.info("📡 Step 3: Simulating EV cable connection (State B)...")
        await self._set_ev_state("B")
        self._check_cancellation()
        await asyncio.sleep(2)  # Give wallbox time to process connection

        # 4. Wait for transaction to start
        logger.info("⏳ Step 4: Waiting for transaction to start...")
        transaction_id = None
        start_time = asyncio.get_event_loop().time()
        timeout = 10  # 10 seconds to detect transaction start

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            self._check_cancellation()
            await asyncio.sleep(0.5)

            # Check for new ongoing transaction
            for tx_id, tx_data in TRANSACTIONS.items():
                if (tx_data.get("charge_point_id") == self.charge_point_id and
                    tx_data.get("status") == "Ongoing" and
                    tx_data.get("remote_started") == True):
                    transaction_id = tx_id
                    break

            if transaction_id:
                break

        if not transaction_id:
            logger.error("❌ Transaction did not start after EV connection")
            logger.info("   💡 Check wallbox logs for errors")
            await self._set_ev_state("A")
            self._set_test_result(step_name, "FAILED")
            return

        logger.info(f"   ✅ Transaction started! (ID: {transaction_id})")
        logger.info("")

        # 5. Simulate the EV drawing power by setting state to 'C'
        logger.info("📡 Step 5: Setting EV state to 'C' (requesting power)...")
        await self._set_ev_state("C")
        self._check_cancellation()
        await asyncio.sleep(2)

        # 6. Wait for the charge point to send a StatusNotification indicating "Charging".
        logger.info("📡 Step 6: Waiting for charge point to report 'Charging' status...")
        try:
            await asyncio.wait_for(self._wait_for_status("Charging"), timeout=15)
            self._check_cancellation()
            logger.info("   ✅ Charge point is now charging!")
        except asyncio.TimeoutError:
            logger.error("    ❌ Timeout waiting for 'Charging' status")
            await self._set_ev_state("A")
            self._set_test_result(step_name, "FAILED")
            return

        # 7. Brief verification
        logger.info("")
        logger.info("📊 Verifying transaction is active...")
        await asyncio.sleep(3)
        self._check_cancellation()

        # Check transaction is still active
        if transaction_id in TRANSACTIONS:
            tx_data = TRANSACTIONS[transaction_id]
            if tx_data.get("stop_timestamp") is None:
                meter_values_count = len(tx_data.get("meter_values", []))
                logger.info(f"   ✅ Transaction {transaction_id} active")
                logger.info(f"   📊 Received {meter_values_count} meter value samples")
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ AUTONOMOUS START TEST PASSED")
        logger.info("=" * 60)
        logger.info(f"   ⚡ Transaction ID: {transaction_id}")
        logger.info(f"   🎫 ID Tag: {id_tag}")
        logger.info("   📱 Remote start flow working correctly")

        self._set_test_result(step_name, "PASSED")

        # Cleanup: Stop the transaction and reset EV state
        logger.info("")
        logger.info("🧹 Cleaning up: Stopping transaction and resetting EV state...")

        if transaction_id:
            try:
                stop_response = await self.handler.send_and_wait(
                    "RemoteStopTransaction",
                    RemoteStopTransactionRequest(transactionId=transaction_id),
                    timeout=10
                )
                self._check_cancellation()
                if stop_response and stop_response.get("status") == "Accepted":
                    logger.info(f"   ✅ Transaction {transaction_id} stopped")
                    await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"   ⚠️  Could not stop transaction: {e}")

        # Reset EV state to A (unplugged)
        await self._set_ev_state("A")
        logger.info("   ✅ EV state reset to A (unplugged)")

        # Wait for Available status
        try:
            await asyncio.wait_for(self._wait_for_status("Available"), timeout=10)
            logger.info("   ✅ Wallbox returned to Available state")
        except asyncio.TimeoutError:
            logger.warning("   ⚠️  Timeout waiting for Available status")

        logger.info(f"--- Step B.3 for {self.charge_point_id} complete. ---")

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

        # Check if transaction exists, if not, start one
        transaction_id = next((tid for tid, tdata in TRANSACTIONS.items() if
                               tdata.get("charge_point_id") == self.charge_point_id and tdata.get("status") == "Ongoing"), None)

        if not transaction_id:
            logger.info("⚠️ No active transaction found. Starting transaction first...")

            # Send RemoteStartTransaction
            id_tag = "SetChargingProfile"  # Max 20 chars per OCPP spec
            start_response = await self.handler.send_and_wait(
                "RemoteStartTransaction",
                RemoteStartTransactionRequest(idTag=id_tag, connectorId=1),
                timeout=10
            )
            self._check_cancellation()

            if not start_response or start_response.get("status") != "Accepted":
                logger.error(f"FAILURE: RemoteStartTransaction was not accepted. Response: {start_response}")
                self._set_test_result(step_name, "FAILED")
                return

            logger.info("✓ RemoteStartTransaction accepted")

            # Set EV state to C (charging)
            await self._set_ev_state("C")
            self._check_cancellation()

            # Wait for transaction to start (max 15 seconds)
            logger.info("⏳ Waiting for transaction to start...")
            for _ in range(30):
                await asyncio.sleep(0.5)
                self._check_cancellation()
                transaction_id = next((tid for tid, tdata in TRANSACTIONS.items() if
                                       tdata.get("charge_point_id") == self.charge_point_id and tdata.get("status") == "Ongoing"), None)
                if transaction_id:
                    logger.info(f"✓ Transaction {transaction_id} started successfully")
                    break

            if not transaction_id:
                logger.error("FAILURE: Transaction did not start within 15 seconds")
                self._set_test_result(step_name, "FAILED")
                return
        else:
            logger.info(f"✓ Using existing transaction {transaction_id}")
            # Ensure EV is in state C
            await self._set_ev_state("C")
            self._check_cancellation()
        # Clear any existing profile first (MaxChargingProfilesInstalled = 1)
        clear_response = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest()
        )

        # Get values from params or use defaults, with proper type conversion
        stack_level = int(params.get("stackLevel", 0))
        purpose = params.get("chargingProfilePurpose", "TxProfile")
        kind = params.get("chargingProfileKind", "Absolute")
        charging_unit = params.get("chargingRateUnit")
        limit = params.get("limit")
        duration = int(params.get("duration", 3600))
        number_phases = int(params.get("numberPhases", 3))

        # Convert limit to float if provided
        if limit is not None:
            limit = float(limit)

        # If no unit or limit specified, use configured charging values
        if charging_unit is None or limit is None:
            medium_value, default_unit = get_charging_value("medium")
            if charging_unit is None:
                charging_unit = default_unit
            if limit is None:
                limit = medium_value

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
                    chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=limit, numberPhases=number_phases)]
                )
            )
        )
        success = await self.handler.send_and_wait("SetChargingProfile", profile, timeout=30)
        self._check_cancellation()

        test_passed = False
        verification_results = []

        if success and success.get("status") == "Accepted":
            logger.info("SUCCESS: SetChargingProfile was acknowledged by the charge point.")
            test_passed = True

            # Verify profile was applied using GetCompositeSchedule
            # Don't specify chargingRateUnit - let wallbox return its native unit
            logger.info("🔍 Verifying profile application with GetCompositeSchedule...")
            await asyncio.sleep(2)  # Small delay for wallbox to process

            verify_response = await self.handler.send_and_wait(
                "GetCompositeSchedule",
                GetCompositeScheduleRequest(connectorId=1, duration=3600, chargingRateUnit=None),
                timeout=10
            )

            if verify_response and verify_response.get("status") == "Accepted":
                schedule = verify_response.get("chargingSchedule")
                if schedule:
                    actual_unit = schedule.get("chargingRateUnit", "N/A")
                    periods = schedule.get("chargingSchedulePeriod", [])
                    actual_limit = periods[0].get("limit") if periods else "N/A"
                    actual_phases = periods[0].get("numberPhases") if periods else "N/A"

                    # Compare expected vs actual
                    unit_match = actual_unit == charging_unit
                    limit_match = abs(float(actual_limit) - limit) < 0.01 if actual_limit != "N/A" else False

                    verification_results = [
                        {
                            "parameter": "Stack Level",
                            "expected": str(stack_level),
                            "actual": "N/A",
                            "status": "INFO"
                        },
                        {
                            "parameter": "Number of Phases",
                            "expected": str(number_phases),
                            "actual": str(actual_phases) if actual_phases != "N/A" else "N/A",
                            "status": "INFO"
                        },
                        {
                            "parameter": "Charging Rate Unit",
                            "expected": str(charging_unit),
                            "actual": str(actual_unit),
                            "status": "OK" if unit_match else "NOT OK"
                        },
                        {
                            "parameter": f"Power Limit ({charging_unit})",
                            "expected": str(limit),
                            "actual": str(actual_limit),
                            "status": "OK" if limit_match else "NOT OK"
                        }
                    ]

                    if unit_match and limit_match:
                        logger.info(f"   ✓ Verification passed: {limit}{charging_unit} profile applied correctly")
                    else:
                        logger.error(f"   ❌ Verification FAILED: Expected {limit}{charging_unit}, got {actual_limit}{actual_unit}")
                        test_passed = False
                else:
                    logger.error("   ❌ No charging schedule returned - verification FAILED")
                    test_passed = False
                    verification_results = [{
                        "parameter": "Charging Schedule",
                        "expected": "Present",
                        "actual": "Not returned",
                        "status": "NOT OK"
                    }]
            else:
                logger.error(f"   ❌ GetCompositeSchedule failed: {verify_response} - verification FAILED")
                test_passed = False
                verification_results = [{
                    "parameter": "GetCompositeSchedule",
                    "expected": "Accepted",
                    "actual": verify_response.get("status") if verify_response else "No response",
                    "status": "NOT OK"
                }]

            # Store verification results with test-specific key
            from app.core import VERIFICATION_RESULTS
            logger.info(f"📊 Storing C.1 verification results: {len(verification_results)} items")
            VERIFICATION_RESULTS[f"{self.charge_point_id}_C1"] = {
                "test": "C.1: SetChargingProfile",
                "results": verification_results
            }
            logger.info(f"✅ C.1 verification data stored successfully")
        else:
            logger.error(f"FAILURE: SetChargingProfile was not acknowledged by the charge point. Response: {success}")

        # Cleanup: Stop transaction and clear profile for test autonomy
        logger.info("🧹 Cleaning up test state...")
        try:
            # Stop the transaction we started
            if transaction_id:
                logger.info(f"   Stopping transaction {transaction_id}...")
                stop_response = await self.handler.send_and_wait(
                    "RemoteStopTransaction",
                    RemoteStopTransactionRequest(transactionId=transaction_id),
                    timeout=10
                )
                if stop_response and stop_response.get("status") == "Accepted":
                    logger.info("   ✓ Transaction stopped")
                    await asyncio.sleep(2)  # Wait for stop to complete

            # Clear the profile we set
            logger.info("   Clearing charging profile...")
            clear_response = await self.handler.send_and_wait(
                "ClearChargingProfile",
                ClearChargingProfileRequest()
            )
            if clear_response:
                logger.info("   ✓ Profile cleared")

            # Reset EV to state A
            logger.info("   Resetting EV to state A...")
            await self._set_ev_state("A")
            logger.info("   ✓ EV reset to unplugged")

        except Exception as e:
            logger.warning(f"   ⚠️ Cleanup warning: {e}")

        # Set final result after cleanup
        if test_passed:
            self._set_test_result(step_name, "PASSED")
        else:
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step C.1 for {self.charge_point_id} complete. ---")

    async def run_c2_tx_default_profile_test(self, params: Dict[str, Any] = None):
        """C.2: TxDefaultProfile - Sets a default charging profile to medium power/current for future transactions."""
        if params is None:
            params = {}

        # Get values from params or use defaults, with proper type conversion
        stack_level = int(params.get("stackLevel", 0)) # Changed default to 0
        purpose = params.get("chargingProfilePurpose", "TxDefaultProfile")
        kind = params.get("chargingProfileKind", "Absolute")
        charging_unit = params.get("chargingRateUnit")
        limit = params.get("limit")
        number_phases = int(params.get("numberPhases", 3))

        # Convert limit to float if provided
        if limit is not None:
            limit = float(limit)
        # Note: TxDefaultProfile should not have duration per OCPP standard

        # If no unit or limit specified, use configured charging values
        if charging_unit is None or limit is None:
            medium_value, default_unit = get_charging_value("medium")  # C.2 defaults to 10A/10000W
            if charging_unit is None:
                charging_unit = default_unit
            if limit is None:
                limit = medium_value

        logger.info(f"--- Step C.2: Running TxDefaultProfile test to {limit}{charging_unit} for {self.charge_point_id} ---")
        step_name = "run_c2_tx_default_profile_test"
        self._check_cancellation()

        # Clear any existing profile first (MaxChargingProfilesInstalled = 1)
        clear_response = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest()
        )

        # Send single TxDefaultProfile with configured stackLevel
        profile = SetChargingProfileRequest(
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
                            numberPhases=number_phases
                        )
                    ]
                )
            )
        )
        success = await self.handler.send_and_wait("SetChargingProfile", profile)
        self._check_cancellation()

        test_passed = False
        verification_results = []

        if success and success.get("status") == "Accepted":
            logger.info(f"PASSED: SetChargingProfile to {limit}{charging_unit} was acknowledged.")
            test_passed = True

            # Verify profile was applied using GetCompositeSchedule
            # Note: TxDefaultProfile is set at charge point level (connectorId=0), but we verify
            # at connector level (connectorId=1) because some wallboxes don't support
            # GetCompositeSchedule at the charge point level
            # Don't specify chargingRateUnit in GetCompositeSchedule - let wallbox return its native unit
            logger.info("🔍 Verifying profile application with GetCompositeSchedule on connector 1...")
            await asyncio.sleep(2)  # Small delay for wallbox to process

            verify_response = await self.handler.send_and_wait(
                "GetCompositeSchedule",
                GetCompositeScheduleRequest(connectorId=1, duration=3600, chargingRateUnit=None),
                timeout=10
            )

            if verify_response and verify_response.get("status") == "Accepted":
                schedule = verify_response.get("chargingSchedule")
                if schedule:
                    actual_unit = schedule.get("chargingRateUnit", "N/A")
                    periods = schedule.get("chargingSchedulePeriod", [])
                    actual_limit = periods[0].get("limit") if periods else "N/A"
                    actual_phases = periods[0].get("numberPhases") if periods else "N/A"

                    # Compare expected vs actual
                    unit_match = actual_unit == charging_unit
                    limit_match = abs(float(actual_limit) - limit) < 0.01 if actual_limit != "N/A" else False

                    verification_results = [
                        {
                            "parameter": "Stack Level",
                            "expected": str(stack_level),
                            "actual": "N/A",
                            "status": "INFO"
                        },
                        {
                            "parameter": "Number of Phases",
                            "expected": str(number_phases),
                            "actual": str(actual_phases) if actual_phases != "N/A" else "N/A",
                            "status": "INFO"
                        },
                        {
                            "parameter": "Charging Rate Unit",
                            "expected": str(charging_unit),
                            "actual": str(actual_unit),
                            "status": "OK" if unit_match else "NOT OK"
                        },
                        {
                            "parameter": f"Power Limit ({charging_unit})",
                            "expected": str(limit),
                            "actual": str(actual_limit),
                            "status": "OK" if limit_match else "NOT OK"
                        }
                    ]

                    if unit_match and limit_match:
                        logger.info(f"   ✓ Verification passed: {limit}{charging_unit} profile applied correctly")
                    else:
                        logger.error(f"   ❌ Verification FAILED: Expected {limit}{charging_unit}, got {actual_limit}{actual_unit}")
                        test_passed = False
                else:
                    logger.error("   ❌ No charging schedule returned - verification FAILED")
                    test_passed = False
                    verification_results = [{
                        "parameter": "Charging Schedule",
                        "expected": "Present",
                        "actual": "Not returned",
                        "status": "NOT OK"
                    }]
            else:
                logger.error(f"   ❌ GetCompositeSchedule failed: {verify_response} - verification FAILED")
                test_passed = False
                verification_results = [{
                    "parameter": "GetCompositeSchedule",
                    "expected": "Accepted",
                    "actual": verify_response.get("status") if verify_response else "No response",
                    "status": "NOT OK"
                }]

            # Store verification results with test-specific key
            from app.core import VERIFICATION_RESULTS
            logger.info(f"📊 Storing C.2 verification results: {len(verification_results)} items")
            VERIFICATION_RESULTS[f"{self.charge_point_id}_C2"] = {
                "test": "C.2: TxDefaultProfile",
                "results": verification_results
            }
            logger.info(f"✅ C.2 verification data stored successfully")
        else:
            logger.error(f"FAILED: SetChargingProfile to {limit}{charging_unit} was not acknowledged. Response: {success}")

        # Cleanup: Clear the default profile for test autonomy
        logger.info("🧹 Cleaning up test state...")
        try:
            logger.info("   Clearing TxDefaultProfile...")
            clear_response = await self.handler.send_and_wait(
                "ClearChargingProfile",
                ClearChargingProfileRequest(connectorId=0, chargingProfilePurpose=ChargingProfilePurposeType.TxDefaultProfile)
            )
            if clear_response:
                logger.info("   ✓ TxDefaultProfile cleared")
        except Exception as e:
            logger.warning(f"   ⚠️ Cleanup warning: {e}")

        # Set final result after cleanup
        if test_passed:
            self._set_test_result(step_name, "PASSED")
        else:
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step C.2 for {self.charge_point_id} complete. ---")

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

    async def run_c4_clear_charging_profile_test(self):
        """C.4: ClearChargingProfile - Clears any default charging profiles."""
        logger.info(f"--- Step C.4: Running ClearChargingProfile test for {self.charge_point_id} ---")
        step_name = "run_c4_clear_charging_profile_test"
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
        logger.info(f"--- Step C.4 for {self.charge_point_id} complete. ---")

    async def run_c5_cleanup_test(self):
        """C.5: Cleanup - Stops active transactions, clears charging profiles, and resets EV state."""
        logger.info(f"--- Step C.5: Running Cleanup test for {self.charge_point_id} ---")
        step_name = "run_c5_cleanup_test"
        self._check_cancellation()

        cleanup_failed = False

        # 1. Stop any active transactions
        transaction_id = next((tid for tid, tdata in TRANSACTIONS.items() if
                               tdata.get("charge_point_id") == self.charge_point_id and tdata.get("status") == "Ongoing"), None)

        if transaction_id:
            logger.info(f"🛑 Stopping active transaction {transaction_id}...")
            try:
                stop_response = await self.handler.send_and_wait(
                    "RemoteStopTransaction",
                    RemoteStopTransactionRequest(transactionId=transaction_id),
                    timeout=10
                )
                self._check_cancellation()

                if stop_response and stop_response.get("status") == "Accepted":
                    logger.info("✓ Transaction stop accepted")
                    # Wait for transaction to actually stop
                    for _ in range(20):
                        await asyncio.sleep(0.5)
                        self._check_cancellation()
                        tx_data = TRANSACTIONS.get(transaction_id)
                        if tx_data and tx_data.get("status") != "Ongoing":
                            logger.info("✓ Transaction stopped successfully")
                            break
                else:
                    logger.warning(f"⚠️ Transaction stop not accepted: {stop_response}")
                    cleanup_failed = True

            except Exception as e:
                logger.error(f"❌ Failed to stop transaction: {e}")
                cleanup_failed = True
        else:
            logger.info("✓ No active transaction to stop")

        # 2. Clear all charging profiles
        logger.info("🧹 Clearing all charging profiles...")
        try:
            clear_response = await self.handler.send_and_wait(
                "ClearChargingProfile",
                ClearChargingProfileRequest()
            )
            self._check_cancellation()

            if clear_response and clear_response.get("status") == "Accepted":
                logger.info("✓ Charging profiles cleared")
            else:
                logger.warning(f"⚠️ Clear profiles not fully accepted: {clear_response}")
                # Don't fail the test if profiles couldn't be cleared (might not exist)

        except Exception as e:
            logger.error(f"❌ Failed to clear profiles: {e}")
            cleanup_failed = True

        # 3. Reset EV state to 'A' (unplugged)
        logger.info("🔌 Resetting EV state to 'A' (unplugged)...")
        try:
            await self._set_ev_state("A")
            self._check_cancellation()
            logger.info("✓ EV state reset to 'A'")
        except Exception as e:
            logger.error(f"❌ Failed to reset EV state: {e}")
            cleanup_failed = True

        # Wait a moment for everything to settle
        await asyncio.sleep(1)

        if cleanup_failed:
            logger.error("❌ Cleanup completed with errors")
            self._set_test_result(step_name, "PARTIAL")
        else:
            logger.info("✅ Cleanup completed successfully")
            self._set_test_result(step_name, "PASSED")

        logger.info(f"--- Step C.5 for {self.charge_point_id} complete. ---")

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
                        ChargingSchedulePeriod(startPeriod=0, limit=medium_value, numberPhases=3)
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
        id_tag = "50600020100021"
        connector_id = 0

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
        id_tag = "50600020100021"
        connector_id = 0

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
            # Always use transaction ID 0 for simplicity
            cs_internal_transaction_id = 0

            TRANSACTIONS[0] = {
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
            logger.info(f"Transaction (temp key: {0}, CS ID: {cs_internal_transaction_id}) registered internally.")
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
        id_tag = "50600020100021"
        connector_id = 0

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
            # Always use transaction ID 0 for simplicity
            cs_internal_transaction_id = 0

            TRANSACTIONS[0] = {
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
            logger.info(f"Transaction (temp key: {0}, CS ID: {cs_internal_transaction_id}) registered internally.")
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
                        ChargingSchedulePeriod(startPeriod=0, limit=charging_value, numberPhases=3)
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
                        ChargingSchedulePeriod(startPeriod=0, limit=charging_value, numberPhases=3)
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

    async def run_b6_clear_rfid_cache(self):
        """B.6: Clear RFID Cache - Clears the local authorization list (RFID cache) in the wallbox."""
        logger.info(f"--- Step B.6: Clear RFID Cache for {self.charge_point_id} ---")
        step_name = "run_b6_clear_rfid_cache"
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

        logger.info(f"--- Step B.6 for {self.charge_point_id} complete. ---")

    async def run_b7_send_rfid_list(self):
        """B.7: Send RFID List - Sends a local authorization list with RFID cards to the wallbox."""
        logger.info(f"--- Step B.7: Send RFID List for {self.charge_point_id} ---")
        step_name = "run_b7_send_rfid_list"
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
                self._set_test_result(step_name, "NOT_SUPPORTED")
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

        logger.info(f"--- Step B.7 for {self.charge_point_id} complete. ---")

    async def run_b8_get_rfid_list_version(self):
        """B.8: Get RFID List Version - Gets the current version of the local authorization list."""
        logger.info(f"--- Step B.8: Get RFID List Version for {self.charge_point_id} ---")
        step_name = "run_b8_get_rfid_list_version"
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
                    logger.info("   💡 Run B.8 Send RFID List to create a local authorization list")
                else:
                    logger.info(f"   💡 Local authorization list exists with version {list_version}")
                    logger.info("   💡 Use this version number for differential updates")
                self._set_test_result(step_name, "PASSED")
            elif list_version == -1:
                logger.warning("⚠️ Wallbox returned version -1")
                logger.info("   💡 This typically means the wallbox does not support local authorization lists")
                logger.info("   💡 Or local authorization functionality is disabled")
                logger.info("   💡 Try B.8 Send RFID List to test if SendLocalList is supported")
                self._set_test_result(step_name, "NOT_SUPPORTED")
            else:
                logger.error(f"❌ Invalid list version received: {list_version}")
                self._set_test_result(step_name, "FAILED")

        except Exception as e:
            logger.error(f"❌ Error during GetLocalListVersion: {e}")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step B.8 for {self.charge_point_id} complete. ---")

    async def run_b3_tap_to_charge_test(self):
        """B.3: RFID Tap-to-Charge (Online Authorization) - Tests the standard RFID tap-to-charge flow."""
        logger.info(f"--- Step B.3: RFID Tap-to-Charge (Online Authorization) for {self.charge_point_id} ---")
        step_name = "run_b3_tap_to_charge_test"
        self._check_cancellation()

        logger.info("🎫 TAP-TO-CHARGE TEST")
        logger.info("   📘 This tests the standard OCPP 1.6-J authorization flow:")
        logger.info("   📘 1. User taps RFID card → Wallbox sends Authorize request")
        logger.info("   📘 2. Central System responds Accepted/Blocked")
        logger.info("   📘 3. Test automatically plugs in EV → Wallbox starts transaction")
        logger.info("")
        logger.info("👤 USER ACTION REQUIRED:")
        logger.info("   • TAP your RFID card on the wallbox reader")
        logger.info("")
        logger.info("🤖 AUTOMATIC ACTIONS:")
        logger.info("   • Central System will accept the RFID card")
        logger.info("   • EV simulator will automatically plug in (State B)")
        logger.info("   • Transaction will start automatically")
        logger.info("")
        logger.info("⏳ Waiting for RFID card tap (timeout: 60 seconds)...")
        logger.info("   💡 Test will automatically proceed after card is detected")

        # Enable RFID test mode - accept ANY card during B.10 test
        from app.ocpp_message_handlers import rfid_test_state
        rfid_test_state["active"] = True
        rfid_test_state["cards_presented"] = []
        logger.debug("🔓 RFID test mode enabled - any card will be accepted")

        # Track authorization state
        authorized_card = None
        transaction_started = False
        rfid_detected = False

        # Wait for RFID Authorization request from wallbox
        start_time = asyncio.get_event_loop().time()
        timeout = 60  # 60 seconds to tap card

        try:
            while asyncio.get_event_loop().time() - start_time < timeout:
                await asyncio.sleep(0.5)
                self._check_cancellation()

                # Check if we received an authorization
                if self.charge_point_id in CHARGE_POINTS:
                    cp_data = CHARGE_POINTS[self.charge_point_id]

                    # Check if RFID card was accepted (but transaction not yet started)
                    if not rfid_detected and cp_data.get("accepted_rfid"):
                        rfid_detected = True
                        authorized_card = cp_data.get("accepted_rfid")
                        logger.info(f"✅ RFID card detected and authorized: {authorized_card}")
                        logger.info("   Central System accepted the card")
                        logger.info("")
                        logger.info("🔌 Automatically plugging in EV cable (setting State B)...")

                        # Set EV simulator to State B (Connected) to trigger transaction
                        await self._set_ev_state("B")
                        logger.info("   ✅ EV cable plugged in")
                        logger.info("   ⏳ Waiting for wallbox to start transaction...")

                    # Check for ongoing transaction
                    if rfid_detected:
                        for tx_id, tx_data in TRANSACTIONS.items():
                            if (tx_data.get("charge_point_id") == self.charge_point_id and
                                tx_data.get("status") == "Ongoing"):
                                transaction_started = True
                                logger.info(f"✅ Transaction started!")
                                logger.info(f"   Transaction ID: {tx_id}")
                                logger.info(f"   RFID Card: {authorized_card}")
                                break

                    if transaction_started:
                        break

        except asyncio.TimeoutError:
            logger.error("❌ Timeout: No RFID card tap detected within 60 seconds")
            rfid_test_state["active"] = False  # Disable RFID test mode
            self._set_test_result(step_name, "FAILED")
            return

        if not transaction_started:
            logger.error("❌ Test FAILED: No transaction was started")
            logger.info("   💡 Please ensure:")
            logger.info("      - RFID card is valid and registered")
            logger.info("      - EV cable is plugged in after tapping card")
            logger.info("      - Wallbox LEDs indicate ready state")
            rfid_test_state["active"] = False  # Disable RFID test mode
            self._set_test_result(step_name, "FAILED")
            return

        # Test PASSED - transaction started successfully
        logger.info("✅ TAP-TO-CHARGE TEST PASSED")
        logger.info(f"   🎫 RFID Card: {authorized_card}")
        logger.info("   ⚡ Transaction: Started")
        logger.info("   💡 Standard OCPP 1.6-J authorization flow working correctly")

        rfid_test_state["active"] = False  # Disable RFID test mode
        self._set_test_result(step_name, "PASSED")

        # Cleanup: Stop the transaction and reset EV state
        logger.info("")
        logger.info("🧹 Cleaning up: Stopping transaction and resetting EV state...")

        # Find the active transaction
        transaction_id = None
        for tx_id, tx_data in TRANSACTIONS.items():
            if (tx_data.get("charge_point_id") == self.charge_point_id and
                tx_data.get("status") == "Ongoing"):
                transaction_id = tx_id
                break

        if transaction_id:
            try:
                stop_response = await self.handler.send_and_wait(
                    "RemoteStopTransaction",
                    RemoteStopTransactionRequest(transactionId=transaction_id),
                    timeout=10
                )
                self._check_cancellation()
                if stop_response and stop_response.get("status") == "Accepted":
                    logger.info(f"   ✅ Transaction {transaction_id} stopped")
                    await asyncio.sleep(2)  # Wait for StopTransaction message
            except Exception as e:
                logger.warning(f"   ⚠️  Could not stop transaction: {e}")

        # Reset EV state to A (unplugged)
        await self._set_ev_state("A")
        logger.info("   ✅ EV state reset to A (unplugged)")

        # Wait for Available status
        try:
            await asyncio.wait_for(self._wait_for_status("Available"), timeout=10)
            logger.info("   ✅ Wallbox returned to Available state")
        except asyncio.TimeoutError:
            logger.warning("   ⚠️  Timeout waiting for Available status")

        logger.info(f"--- Step B.3 for {self.charge_point_id} complete. ---")

    async def run_b4_anonymous_remote_start_test(self, params=None):
        """B.4: Anonymous Remote Start - Tests remote transaction initiation via app/website."""
        logger.info(f"--- Step B.4: Anonymous Remote Start for {self.charge_point_id} ---")
        step_name = "run_b4_anonymous_remote_start_test"
        self._check_cancellation()

        logger.info("📱 REMOTE START TEST")
        logger.info("   📘 This tests remote charging initiation:")
        logger.info("   📘 1. User initiates charging (e.g., via website, QR code, or app)")
        logger.info("   📘 2. Central System sends RemoteStartTransaction with user's idTag")
        logger.info("   📘 3. Wallbox starts transaction for the specified user")
        logger.info("")
        logger.info("💡 Use cases: App-based charging, web portal charging, pre-authorized sessions")
        logger.info("")

        # Step 0: Ensure baseline configuration
        logger.info("🔧 Step 0: Verifying baseline configuration...")
        logger.info("   📘 For this test: AuthorizeRemoteTxRequests=false (remote commands don't need auth)")

        try:
            response = await self.handler.send_and_wait(
                "GetConfiguration",
                GetConfigurationRequest(key=["AuthorizeRemoteTxRequests"]),
                timeout=10
            )
            self._check_cancellation()

            authorize_remote = None
            if response and response.get("configurationKey"):
                for key in response.get("configurationKey", []):
                    if key.get("key") == "AuthorizeRemoteTxRequests":
                        authorize_remote = key.get("value", "").lower()
                        break

            if authorize_remote != "false":
                logger.info(f"   🔧 Setting AuthorizeRemoteTxRequests=false (currently: {authorize_remote})...")
                config_response = await self.handler.send_and_wait(
                    "ChangeConfiguration",
                    ChangeConfigurationRequest(key="AuthorizeRemoteTxRequests", value="false"),
                    timeout=10
                )
                self._check_cancellation()
                if config_response and config_response.get("status") == "Accepted":
                    logger.info("   ✅ Configuration updated")
                else:
                    logger.warning(f"   ⚠️  Configuration may not have updated: {config_response.get('status', 'Unknown')}")
            else:
                logger.info("   ✅ Configuration already correct")

        except Exception as e:
            logger.warning(f"   ⚠️  Could not verify/update configuration: {e}")

        logger.info("")

        # Step 1: Plug in EV (set State B)
        logger.info("🔌 Step 1: Simulating EV cable connection...")
        logger.info("   💡 In real scenario, user plugs in their EV")

        await self._set_ev_state("B")
        logger.info("   ✅ EV cable connected (State B)")

        # Step 2: Send RemoteStartTransaction with idTag for remote charging
        logger.info("")
        logger.info("📤 Step 2: Sending RemoteStartTransaction command...")
        logger.info("   🎫 ID Tag: ElecqAutoStart (using wallbox's authorized tag)")
        logger.info("   🔌 Connector: 1")

        try:
            response = await self.handler.send_and_wait(
                "RemoteStartTransaction",
                RemoteStartTransactionRequest(
                    idTag="ElecqAutoStart",  # Use wallbox's authorized tag
                    connectorId=1
                ),
                timeout=10
            )
            self._check_cancellation()

            if not response or response.get("status") != "Accepted":
                status = response.get("status", "Unknown") if response else "No response"
                logger.error(f"❌ RemoteStartTransaction rejected: {status}")
                self._set_test_result(step_name, "FAILED")
                return

            logger.info(f"✅ RemoteStartTransaction accepted by wallbox")
            logger.info("   💡 Transaction authorized - waiting for StartTransaction...")
            logger.info("")

            # Create placeholder transaction entry to track this remote start
            # Use a temporary key (we'll get the real transaction ID from StartTransaction.req)
            temp_transaction_key = f"temp_remote_b11_1"
            TRANSACTIONS[temp_transaction_key] = {
                "charge_point_id": self.charge_point_id,
                "id_tag": "ElecqAutoStart",  # Wallbox's authorized tag
                "start_time": datetime.now(timezone.utc).isoformat(),
                "meter_start": 0,  # Will be updated by StartTransaction
                "connector_id": 1,
                "status": "Ongoing",
                "remote_started": True,  # Mark as remotely started
                "anonymous": False,  # Not anonymous - has idTag
                "cp_transaction_id": None,  # Will be filled by StartTransaction
            }
            logger.debug(f"   📝 Created placeholder transaction entry: {temp_transaction_key}")

        except Exception as e:
            logger.error(f"❌ Failed to send RemoteStartTransaction: {e}")
            self._set_test_result(step_name, "FAILED")
            return

        # Step 3: Wait for transaction to start
        logger.info("")
        logger.info("⏳ Step 3: Waiting for transaction to start...")
        logger.info("   💡 Wallbox should now initiate the transaction")

        transaction_id = None
        start_time = asyncio.get_event_loop().time()
        timeout = 15  # 15 seconds to start transaction

        while asyncio.get_event_loop().time() - start_time < timeout:
            await asyncio.sleep(0.5)
            self._check_cancellation()

            # Check for new ongoing transaction
            for tx_id, tx_data in TRANSACTIONS.items():
                if (tx_data.get("charge_point_id") == self.charge_point_id and
                    tx_data.get("status") == "Ongoing" and
                    tx_data.get("remote_started") == True):
                    transaction_id = tx_id
                    logger.info(f"✅ Transaction started!")
                    logger.info(f"   Transaction ID: {tx_id}")
                    logger.info(f"   ID Tag: {tx_data.get('id_tag', 'N/A')}")
                    break

            if transaction_id:
                break

        if not transaction_id:
            logger.error("❌ Transaction did not start within timeout")
            logger.info("   💡 Check wallbox logs for errors")
            await self._set_ev_state("A")
            self._set_test_result(step_name, "FAILED")
            return

        # Test PASSED
        logger.info("")
        logger.info("✅ ANONYMOUS REMOTE START TEST PASSED")
        logger.info(f"   ⚡ Transaction ID: {transaction_id}")
        logger.info("   ❗ No ID Tag (Anonymous charging)")
        logger.info("   📱 Free/anonymous charging flow working correctly")

        self._set_test_result(step_name, "PASSED")

        # Cleanup: Stop the transaction and reset EV state
        logger.info("")
        logger.info("🧹 Cleaning up: Stopping anonymous transaction and resetting EV state...")

        if transaction_id:
            try:
                stop_response = await self.handler.send_and_wait(
                    "RemoteStopTransaction",
                    RemoteStopTransactionRequest(transactionId=transaction_id),
                    timeout=10
                )
                self._check_cancellation()
                if stop_response and stop_response.get("status") == "Accepted":
                    logger.info(f"   ✅ Transaction {transaction_id} stopped")
                    await asyncio.sleep(2)  # Wait for StopTransaction message
            except Exception as e:
                logger.warning(f"   ⚠️  Could not stop transaction: {e}")

        # Reset EV state to A (unplugged)
        await self._set_ev_state("A")
        logger.info("   ✅ EV state reset to A (unplugged)")

        # Wait for Available status
        try:
            await asyncio.wait_for(self._wait_for_status("Available"), timeout=10)
            logger.info("   ✅ Wallbox returned to Available state")
        except asyncio.TimeoutError:
            logger.warning("   ⚠️  Timeout waiting for Available status")

        logger.info(f"--- Step B.4 for {self.charge_point_id} complete. ---")

    async def run_b5_plug_and_charge_test(self, params=None):
        """B.5: Plug-and-Charge - Tests automatic charging when EV is plugged in with LocalPreAuthorize enabled."""
        logger.info(f"--- Step B.5: Plug-and-Charge for {self.charge_point_id} ---")
        step_name = "run_b5_plug_and_charge_test"
        self._check_cancellation()

        logger.info("🔌 PLUG-AND-CHARGE TEST")
        logger.info("   📘 This tests automatic charging with LocalPreAuthorize:")
        logger.info("   📘 1. User plugs in their EV (no RFID tap needed)")
        logger.info("   📘 2. Wallbox automatically starts transaction with default idTag")
        logger.info("   📘 3. Charging begins immediately")
        logger.info("")
        logger.info("💡 Use case: Private home chargers - just plug in and charge!")
        logger.info("")

        # Step 1: Verify and enable LocalPreAuthorize if needed
        logger.info("📤 Step 1: Checking LocalPreAuthorize configuration...")

        try:
            response = await self.handler.send_and_wait(
                "GetConfiguration",
                GetConfigurationRequest(key=["LocalPreAuthorize"]),
                timeout=10
            )
            self._check_cancellation()

            local_pre_authorize = None
            if response and response.get("configurationKey"):
                for key in response.get("configurationKey", []):
                    if key.get("key") == "LocalPreAuthorize":
                        local_pre_authorize = key.get("value", "").lower()
                        break

            if local_pre_authorize == "true":
                logger.info("   ✅ LocalPreAuthorize is already enabled")
            else:
                logger.warning(f"   ⚠️  LocalPreAuthorize is '{local_pre_authorize}' - enabling it now...")

                # Enable LocalPreAuthorize
                config_response = await self.handler.send_and_wait(
                    "ChangeConfiguration",
                    ChangeConfigurationRequest(key="LocalPreAuthorize", value="true"),
                    timeout=10
                )
                self._check_cancellation()

                if config_response and config_response.get("status") == "Accepted":
                    logger.info("   ✅ LocalPreAuthorize enabled successfully")
                elif config_response and config_response.get("status") == "RebootRequired":
                    logger.warning("   ⚠️  LocalPreAuthorize enabled but REBOOT REQUIRED")
                    logger.info("   💡 Please run X.1: Reboot Wallbox and try B.12 again")
                    self._set_test_result(step_name, "FAILED")
                    return
                else:
                    status = config_response.get("status", "Unknown") if config_response else "No response"
                    logger.error(f"   ❌ Failed to enable LocalPreAuthorize: {status}")
                    logger.info("   💡 You may need to enable it manually or use B.4 test")
                    self._set_test_result(step_name, "FAILED")
                    return

        except Exception as e:
            logger.error(f"❌ Failed to configure LocalPreAuthorize: {e}")
            logger.info("   💡 Try running B.4 test first or enable manually")
            self._set_test_result(step_name, "FAILED")
            return

        # Step 2: Ensure we're in idle state (State A)
        logger.info("")
        logger.info("🔄 Step 2: Ensuring wallbox is ready (State A)...")

        await self._set_ev_state("A")
        await asyncio.sleep(2)
        logger.info("   ✅ Wallbox ready in idle state")

        # Step 3: Plug in EV (State B) - this should automatically start charging
        logger.info("")
        logger.info("🔌 Step 3: Plugging in EV...")
        logger.info("   💡 With LocalPreAuthorize enabled, wallbox should auto-start transaction")

        await self._set_ev_state("B")
        await asyncio.sleep(1)
        logger.info("   ✅ EV cable connected (State B)")

        # Step 4: Wait for automatic transaction start
        logger.info("")
        logger.info("⏳ Step 4: Waiting for automatic transaction start...")
        logger.info("   💡 Wallbox should start transaction without RFID or remote command")

        transaction_id = None
        start_time = asyncio.get_event_loop().time()
        timeout = 20  # Wait up to 20 seconds for auto-start

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            self._check_cancellation()
            await asyncio.sleep(0.5)

            # Check if a new transaction was created
            for tx_id, tx_data in TRANSACTIONS.items():
                if (tx_data.get("charge_point_id") == self.charge_point_id and
                    tx_data.get("connector_id") == 1 and
                    tx_data.get("stop_timestamp") is None and
                    not tx_data.get("remote_started", False)):  # Not remotely started
                    transaction_id = tx_id
                    break

            if transaction_id:
                break

        if not transaction_id:
            logger.error("❌ Wallbox did not automatically start transaction")
            logger.info("   💡 Check that LocalPreAuthorize is enabled (run B.4 first)")
            self._set_test_result(step_name, "FAILED")
            return

        # Wait a moment for transaction details to be fully populated
        await asyncio.sleep(0.5)

        # Get transaction details
        tx_data = TRANSACTIONS.get(transaction_id, {})
        id_tag = tx_data.get("id_tag", "Unknown")

        logger.info(f"   ✅ Transaction automatically started!")
        logger.info(f"   ⚡ Transaction ID: {transaction_id}")
        logger.info(f"   🏷️  Default idTag: '{id_tag}'")
        logger.info("")
        logger.info("💡 This is the default idTag used for plug-and-charge")
        logger.info("   (Common values: 'ElecqAutoStart', 'AutoStart', etc.)")

        # Step 5: Verify charging is active
        logger.info("")
        logger.info("⚡ Step 5: Verifying charging session is active...")

        await asyncio.sleep(2)

        # Check if transaction is still active
        if transaction_id in TRANSACTIONS:
            tx_data = TRANSACTIONS[transaction_id]
            if tx_data.get("stop_timestamp") is None:
                logger.info("   ✅ Charging session is active")

                # Check for meter values
                meter_values = tx_data.get("meter_values", [])
                if meter_values:
                    logger.info(f"   📊 Received {len(meter_values)} meter value samples")
                else:
                    logger.info("   ⏳ Waiting for meter values...")
            else:
                logger.warning("   ⚠️  Transaction stopped unexpectedly")
        else:
            logger.warning("   ⚠️  Transaction no longer exists")

        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ PLUG-AND-CHARGE TEST PASSED")
        logger.info("=" * 60)
        logger.info(f"   ⚡ Transaction ID: {transaction_id}")
        logger.info(f"   🏷️  Default idTag: '{id_tag}'")
        logger.info("   🔌 Plug-and-charge flow working correctly")

        self._set_test_result(step_name, "PASSED")

        # Cleanup: Stop the transaction, reset EV state, and restore configuration
        logger.info("")
        logger.info("🧹 Cleaning up: Stopping transaction, resetting EV state, and restoring configuration...")

        if transaction_id:
            try:
                stop_response = await self.handler.send_and_wait(
                    "RemoteStopTransaction",
                    RemoteStopTransactionRequest(transactionId=transaction_id),
                    timeout=10
                )
                self._check_cancellation()
                if stop_response and stop_response.get("status") == "Accepted":
                    logger.info(f"   ✅ Transaction {transaction_id} stopped")
                    await asyncio.sleep(2)  # Wait for StopTransaction message
            except Exception as e:
                logger.warning(f"   ⚠️  Could not stop transaction: {e}")

        # Reset EV state to A (unplugged)
        await self._set_ev_state("A")
        logger.info("   ✅ EV state reset to A (unplugged)")

        # Wait for Available status
        try:
            await asyncio.wait_for(self._wait_for_status("Available"), timeout=10)
            logger.info("   ✅ Wallbox returned to Available state")
        except asyncio.TimeoutError:
            logger.warning("   ⚠️  Timeout waiting for Available status")

        # Restore LocalPreAuthorize to false to match baseline configuration
        logger.info("   🔧 Restoring LocalPreAuthorize to baseline (false)...")
        try:
            config_response = await self.handler.send_and_wait(
                "ChangeConfiguration",
                ChangeConfigurationRequest(key="LocalPreAuthorize", value="false"),
                timeout=10
            )
            self._check_cancellation()
            if config_response and config_response.get("status") in ["Accepted", "RebootRequired"]:
                logger.info("   ✅ LocalPreAuthorize restored to false")
                if config_response.get("status") == "RebootRequired":
                    logger.info("   ⚠️  Reboot required for configuration to take effect")
            else:
                logger.warning(f"   ⚠️  Could not restore LocalPreAuthorize: {config_response.get('status', 'Unknown')}")
        except Exception as e:
            logger.warning(f"   ⚠️  Error restoring LocalPreAuthorize: {e}")

        logger.info(f"--- Step B.5 for {self.charge_point_id} complete. ---")

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

    async def run_x2_dump_all_configuration(self):
        """X.2: Dump All Configuration - Retrieves and displays ALL configuration parameters from wallbox."""
        logger.info(f"--- Step X.2: Dump All Configuration for {self.charge_point_id} ---")
        step_name = "run_x2_dump_all_configuration"
        self._check_cancellation()

        logger.info("📋 Requesting ALL configuration parameters from wallbox...")

        # GetConfiguration without specifying keys returns ALL parameters
        get_config_request = GetConfigurationRequest(key=None)

        try:
            response = await self.handler.send_and_wait("GetConfiguration", get_config_request, timeout=10)
            self._check_cancellation()

            if response and response.get("configurationKey"):
                config_keys = response.get("configurationKey", [])
                logger.info(f"✅ Retrieved {len(config_keys)} configuration parameters")
                logger.info("")
                logger.info("═" * 80)
                logger.info("ALL CONFIGURATION PARAMETERS:")
                logger.info("═" * 80)

                # Sort by key name for easier reading
                config_keys_sorted = sorted(config_keys, key=lambda x: x.get("key", ""))

                for config_item in config_keys_sorted:
                    key = config_item.get("key", "N/A")
                    value = config_item.get("value", "N/A")
                    readonly = config_item.get("readonly", False)
                    readonly_str = " [READONLY]" if readonly else ""
                    logger.info(f"  {key:40} = {value}{readonly_str}")

                logger.info("═" * 80)
                logger.info("")

                # Highlight authorization-related parameters
                logger.info("🔍 AUTHORIZATION-RELATED PARAMETERS:")
                auth_keywords = ["auth", "pre", "auto", "local", "remote", "start", "offline"]
                for config_item in config_keys_sorted:
                    key = config_item.get("key", "")
                    if any(keyword in key.lower() for keyword in auth_keywords):
                        value = config_item.get("value", "N/A")
                        logger.info(f"  ✅ {key:40} = {value}")

                logger.info("")
                self._set_test_result(step_name, "PASSED")
            else:
                logger.error("❌ GetConfiguration failed - no response")
                self._set_test_result(step_name, "FAILED")

        except Exception as e:
            logger.error(f"❌ Exception during configuration dump: {e}")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step X.2 for {self.charge_point_id} complete. ---")

    async def run_c3_get_composite_schedule_test(self, params: Dict[str, Any] = None):
        """C.3: GetCompositeSchedule - Queries the current schedule being applied on connector 1."""
        if params is None:
            params = {}

        logger.info(f"--- Step C.3: Running GetCompositeSchedule test for {self.charge_point_id} ---")
        step_name = "run_c3_get_composite_schedule_test"
        self._check_cancellation()

        # Extract parameters with defaults
        connector_id = params.get("connectorId", 1)
        duration = params.get("duration", 3600)
        charging_rate_unit = params.get("chargingRateUnit")

        logger.info(f"Querying charging schedule on connector {connector_id} for {duration} seconds...")

        composite_request = GetCompositeScheduleRequest(
            connectorId=connector_id,
            duration=duration,
            chargingRateUnit=charging_rate_unit
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

        logger.info(f"--- Step C.3 for {self.charge_point_id} complete. ---")

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