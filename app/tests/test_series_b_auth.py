"""
OCPP Test Series B: Authorization & Status Management

This module contains all B-series tests related to:
- RFID authorization (online and offline)
- Local cache authorization
- Remote start transactions
- Plug-and-charge (LocalPreAuthorize)
- RFID list management (SendLocalList, GetLocalListVersion, ClearCache)
- Transaction management

Test Methods:
- B.1 (run_b1_reset_transaction_management): Reset baseline configuration
- B.1 (run_b1_rfid_public_charging_test): RFID before plug-in (online auth)
- B.2 (run_b2_local_cache_authorization_test): RFID after plug-in (local cache)
- B.3 (run_b3_remote_smart_charging_test): Remote start transaction
- B.4 (run_b4_offline_local_start_test): Plug-and-charge (LocalPreAuthorize)
- B.6 (run_b6_clear_rfid_cache): Clear RFID cache
- B.7 (run_b7_send_rfid_list): Send local authorization list
- B.8 (run_b8_get_rfid_list_version): Get list version
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.core import (
    CHARGE_POINTS, TRANSACTIONS, OCPP_MESSAGE_TIMEOUT
)
from app.messages import (
    GetConfigurationRequest, ChangeConfigurationRequest,
    RemoteStartTransactionRequest, RemoteStopTransactionRequest,
    ClearCacheRequest, SendLocalListRequest, GetLocalListVersionRequest,
    AuthorizationData, IdTagInfo, UpdateType,
)
from app.test_helpers import (
    # Transaction management
    stop_active_transaction,
    wait_for_transaction_start,
    # Configuration management
    ensure_configuration,
    # EV connection management
    prepare_ev_connection,
    # Cleanup operations
    cleanup_transaction_and_state,
)
from app.tests.test_base import OcppTestBase

if TYPE_CHECKING:
    from app.ocpp_server_logic import OcppServerLogic

logger = logging.getLogger(__name__)


class TestSeriesB(OcppTestBase):
    """
    Test Series B: Authorization & Status Management (8 tests)

    Covers RFID authorization, remote start, plug-and-charge, and local cache management.
    """

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
            response = await self.handler.send_and_wait("ClearCache", clear_cache_request, timeout=OCPP_MESSAGE_TIMEOUT)

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
                response = await self.handler.send_and_wait("ChangeConfiguration", config_request, timeout=OCPP_MESSAGE_TIMEOUT)
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
            response = await self.handler.send_and_wait("GetConfiguration", get_config_request, timeout=OCPP_MESSAGE_TIMEOUT)
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
            response = await self.handler.send_and_wait("ClearCache", clear_cache_request, timeout=OCPP_MESSAGE_TIMEOUT)

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
            response = await self.handler.send_and_wait("GetLocalListVersion", get_version_request, timeout=OCPP_MESSAGE_TIMEOUT)

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

    async def run_b1_rfid_public_charging_test(self):
        """B.1: RFID Authorization Before Plug-in - Tests online authorization before EV connection."""
        logger.info(f"--- Step B.1: RFID Authorization Before Plug-in for {self.charge_point_id} ---")
        step_name = "run_b1_rfid_public_charging_test"
        self._check_cancellation()

        logger.info("🎫 RFID AUTHORIZATION BEFORE PLUG-IN TEST")
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
                    timeout=OCPP_MESSAGE_TIMEOUT
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
            await asyncio.wait_for(self._wait_for_status("Available"), timeout=OCPP_MESSAGE_TIMEOUT)
            logger.info("   ✅ Wallbox returned to Available state")
        except asyncio.TimeoutError:
            logger.warning("   ⚠️  Timeout waiting for Available status")

        logger.info(f"--- Step B.1 for {self.charge_point_id} complete. ---")

    async def run_b2_local_cache_authorization_test(self):
        """B.2: RFID Authorization After Plug-in - Tests local cache authorization with EV already connected."""
        logger.info(f"--- Step B.2: RFID Authorization After Plug-in for {self.charge_point_id} ---")
        step_name = "run_b2_local_cache_authorization_test"
        self._check_cancellation()

        logger.info("🎫 RFID AUTHORIZATION AFTER PLUG-IN TEST (Local Cache)")
        logger.info("   📘 This tests OCPP local authorization list capability:")
        logger.info("   📘 1. User plugs in EV first")
        logger.info("   📘 2. User taps RFID card")
        logger.info("   📘 3. Wallbox checks local cache → immediate start if found")
        logger.info("   📘 4. No network delay for known users")
        logger.info("")

        # Step 0: Ensure local auth list is enabled
        logger.info("🔧 Step 0: Verifying local authorization list configuration...")
        try:
            response = await self.handler.send_and_wait(
                "GetConfiguration",
                GetConfigurationRequest(key=["LocalAuthListEnabled", "LocalAuthorizeOffline"]),
                timeout=OCPP_MESSAGE_TIMEOUT
            )
            self._check_cancellation()

            local_list_enabled = None
            local_auth_offline = None
            if response and response.get("configurationKey"):
                for key in response.get("configurationKey", []):
                    if key.get("key") == "LocalAuthListEnabled":
                        local_list_enabled = key.get("value", "").lower()
                    elif key.get("key") == "LocalAuthorizeOffline":
                        local_auth_offline = key.get("value", "").lower()

            logger.info(f"   📋 LocalAuthListEnabled: {local_list_enabled}")
            logger.info(f"   📋 LocalAuthorizeOffline: {local_auth_offline}")

            if local_list_enabled != "true":
                logger.warning("   ⚠️  LocalAuthListEnabled is not true - test may not work as expected")
                logger.warning("   💡 Consider running B.7 (Send RFID List) first")

        except Exception as e:
            logger.warning(f"   ⚠️  Could not verify configuration: {e}")

        logger.info("")

        # Step 1: Plug in EV first (before RFID tap)
        logger.info("📡 Step 1: Simulating EV cable connection (State B)...")
        await self._set_ev_state("B")
        self._check_cancellation()
        await asyncio.sleep(2)  # Give wallbox time to process connection
        logger.info("   ✅ EV connected (cable plugged in)")
        logger.info("")

        # Step 2: Wait for RFID tap
        logger.info("👤 Step 2: USER ACTION REQUIRED:")
        logger.info("   • TAP your RFID card on the wallbox reader")
        logger.info("   • The test will wait up to 60 seconds for card tap...")
        logger.info("")

        # Wait for Authorize message
        start_time = asyncio.get_event_loop().time()
        timeout = 60  # 60 seconds for user to tap card
        authorized_id_tag = None

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            self._check_cancellation()
            await asyncio.sleep(0.5)

            # Check if an Authorize was received (stored in charge point data)
            cp_data = CHARGE_POINTS.get(self.charge_point_id, {})
            authorized_id_tag = cp_data.get("accepted_rfid")

            if authorized_id_tag:
                logger.info(f"   ✅ RFID card detected: {authorized_id_tag}")
                break

        if not authorized_id_tag:
            logger.error("❌ No RFID card tap detected within 60 seconds")
            logger.error("   💡 Please tap your RFID card and try again")
            await self._set_ev_state("A")
            self._set_test_result(step_name, "FAILED")
            return

        # Step 3: Wait for transaction to start (should be quick with local cache)
        logger.info("")
        logger.info("⏳ Step 3: Waiting for transaction to start...")
        logger.info("   💡 With local cache, this should be immediate (< 1 second)")

        transaction_start_time = asyncio.get_event_loop().time()
        transaction_id = None
        start_wait_time = asyncio.get_event_loop().time()
        tx_timeout = 10  # 10 seconds max

        while (asyncio.get_event_loop().time() - start_wait_time) < tx_timeout:
            self._check_cancellation()
            await asyncio.sleep(0.5)

            # Check for new ongoing transaction
            for tx_id, tx_data in TRANSACTIONS.items():
                if (tx_data.get("charge_point_id") == self.charge_point_id and
                    tx_data.get("status") == "Ongoing" and
                    tx_data.get("id_tag") == authorized_id_tag):
                    transaction_id = tx_id
                    transaction_start_delay = asyncio.get_event_loop().time() - transaction_start_time
                    break

            if transaction_id:
                break

        if not transaction_id:
            logger.error("❌ Transaction did not start")
            logger.info("   💡 Possible reasons:")
            logger.info("   • RFID card not in local authorization list")
            logger.info("   • LocalAuthListEnabled is false")
            logger.info("   • Run B.7 (Send RFID List) to add your card")
            await self._set_ev_state("A")
            self._set_test_result(step_name, "FAILED")
            return

        logger.info(f"   ✅ Transaction started! (ID: {transaction_id})")
        logger.info(f"   ⚡ Start delay: {transaction_start_delay:.2f} seconds")

        if transaction_start_delay < 2.0:
            logger.info("   🚀 Fast start detected - local cache working correctly!")
        else:
            logger.warning(f"   ⚠️  Slow start ({transaction_start_delay:.2f}s) - may indicate online authorization")

        logger.info("")

        # Step 4: Set EV state to charging
        logger.info("📡 Step 4: Setting EV state to 'C' (requesting power)...")
        await self._set_ev_state("C")
        self._check_cancellation()
        await asyncio.sleep(2)

        # Step 5: Wait for charging status
        logger.info("📡 Step 5: Waiting for charge point to report 'Charging' status...")
        try:
            await asyncio.wait_for(self._wait_for_status("Charging"), timeout=15)
            self._check_cancellation()
            logger.info("   ✅ Charge point is now charging!")
        except asyncio.TimeoutError:
            logger.error("    ❌ Timeout waiting for 'Charging' status")
            await self._set_ev_state("A")
            self._set_test_result(step_name, "FAILED")
            return

        # Step 6: Brief verification
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
        logger.info("✅ LOCAL CACHE AUTHORIZATION TEST PASSED")
        logger.info("=" * 60)
        logger.info(f"   ⚡ Transaction ID: {transaction_id}")
        logger.info(f"   🎫 ID Tag: {authorized_id_tag}")
        logger.info(f"   ⚡ Start delay: {transaction_start_delay:.2f} seconds")
        logger.info("   📱 Plug-first flow working correctly")

        self._set_test_result(step_name, "PASSED")

        # Cleanup: Stop the transaction and reset EV state
        logger.info("")
        logger.info("🧹 Cleaning up: Stopping transaction and resetting EV state...")

        if transaction_id:
            try:
                stop_response = await self.handler.send_and_wait(
                    "RemoteStopTransaction",
                    RemoteStopTransactionRequest(transactionId=transaction_id),
                    timeout=OCPP_MESSAGE_TIMEOUT
                )
                self._check_cancellation()
                if stop_response and stop_response.get("status") == "Accepted":
                    logger.info("   ✅ Stop command accepted")
                    await asyncio.sleep(3)  # Wait for StopTransaction message
                else:
                    logger.warning(f"   ⚠️  Stop command status: {stop_response.get('status', 'Unknown')}")
            except Exception as e:
                logger.warning(f"   ⚠️  Could not stop transaction: {e}")

        # Reset EV state
        await self._set_ev_state("A")
        await asyncio.sleep(1)

        # Wait for Available status
        try:
            await asyncio.wait_for(self._wait_for_status("Available"), timeout=OCPP_MESSAGE_TIMEOUT)
            logger.info("   ✅ Wallbox returned to Available state")
        except asyncio.TimeoutError:
            logger.warning("   ⚠️  Timeout waiting for Available status")

        logger.info(f"--- Step B.2 for {self.charge_point_id} complete. ---")

    async def run_b3_remote_smart_charging_test(self, params=None):
        """B.3: Remote Smart Charging - Tests remote transaction initiation via app/website."""
        logger.info(f"--- Step B.3: Remote Smart Charging for {self.charge_point_id} ---")
        step_name = "run_b3_remote_smart_charging_test"
        self._check_cancellation()

        logger.info("📱 REMOTE START TEST")
        logger.info("   📘 This tests remote charging initiation:")
        logger.info("   📘 1. User initiates charging (e.g., via website, QR code, or app)")
        logger.info("   📘 2. Central System sends RemoteStartTransaction with user's idTag")
        logger.info("   📘 3. Wallbox starts transaction for the specified user")
        logger.info("")
        logger.info("💡 Use cases: App-based charging, web portal charging, pre-authorized sessions")
        logger.info("")

        # Step -1: Cleanup - Stop any active transactions first
        logger.info("🧹 Step -1: Checking for and stopping any active transactions...")
        await stop_active_transaction(self.handler, self.charge_point_id)
        self._check_cancellation()
        logger.info("")

        # Step 0: Ensure baseline configuration
        logger.info("🔧 Step 0: Verifying baseline configuration...")
        logger.info("   📘 For this test: AuthorizeRemoteTxRequests=true (wallbox checks authorization)")
        logger.info("   📘 This follows standard OCPP 1.6-J Remote Start sequence:")
        logger.info("   📘   1. CS sends RemoteStartTransaction with idTag")
        logger.info("   📘   2. CP sends Authorize to check idTag")
        logger.info("   📘   3. CS responds Authorize.conf (Accepted)")
        logger.info("   📘   4. CP sends StartTransaction")

        await ensure_configuration(self.handler, "AuthorizeRemoteTxRequests", "true")
        self._check_cancellation()
        logger.info("")

        # Step 1: Prepare EV connection (State B)
        success, message = await prepare_ev_connection(
            self.handler,
            self.charge_point_id,
            self.ocpp_server_logic,
            required_status="Preparing",
            timeout=120.0
        )
        self._check_cancellation()

        if not success:
            logger.error(f"   ❌ {message}")
            logger.error("   💡 RemoteStartTransaction requires EV to be plugged in first")
            self._set_test_result(step_name, "FAILED")
            return

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
                timeout=OCPP_MESSAGE_TIMEOUT
            )
            self._check_cancellation()

            if not response or response.get("status") != "Accepted":
                status = response.get("status", "Unknown") if response else "No response"
                logger.error(f"❌ RemoteStartTransaction rejected: {status}")
                logger.info("   💡 Possible reasons for rejection:")
                logger.info("      - Connector already in use or faulted")
                logger.info("      - Wallbox doesn't recognize idTag 'ElecqAutoStart'")
                logger.info("      - Remote start not enabled in wallbox configuration")
                logger.info("      - Wallbox in error state or offline")
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

        transaction_id = await wait_for_transaction_start(
            self.charge_point_id,
            timeout=15.0,
            check_interval=0.5,
            remote_started=True
        )
        self._check_cancellation()

        if not transaction_id:
            logger.error("❌ Transaction did not start within timeout")
            logger.info("   💡 Check wallbox logs for errors")
            await self._set_ev_state("A")
            self._set_test_result(step_name, "FAILED")
            return

        # Log success
        tx_data = TRANSACTIONS.get(transaction_id, {})
        logger.info(f"✅ Transaction started!")
        logger.info(f"   Transaction ID: {transaction_id}")
        logger.info(f"   ID Tag: {tx_data.get('id_tag', 'N/A')}")

        # Test PASSED
        logger.info("")
        logger.info("✅ REMOTE SMART CHARGING TEST PASSED")
        logger.info(f"   ⚡ Transaction ID: {transaction_id}")
        logger.info(f"   🎫 ID Tag: ElecqAutoStart (authorized remotely)")
        logger.info("   📱 Smart charging / remote start flow working correctly")

        self._set_test_result(step_name, "PASSED")

        # Cleanup: Stop the transaction and reset EV state
        logger.info("")
        await cleanup_transaction_and_state(
            self.handler,
            self.charge_point_id,
            self.ocpp_server_logic,
            transaction_id=transaction_id
        )

        logger.info(f"--- Step B.3 for {self.charge_point_id} complete. ---")

    async def run_b4_offline_local_start_test(self, params=None):
        """B.4: Plug & Charge - Tests automatic charging when EV is plugged in with LocalPreAuthorize enabled."""
        logger.info(f"--- Step B.4: Plug & Charge for {self.charge_point_id} ---")
        step_name = "run_b4_offline_local_start_test"
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
                timeout=OCPP_MESSAGE_TIMEOUT
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
                    timeout=OCPP_MESSAGE_TIMEOUT
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
                    timeout=OCPP_MESSAGE_TIMEOUT
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
            await asyncio.wait_for(self._wait_for_status("Available"), timeout=OCPP_MESSAGE_TIMEOUT)
            logger.info("   ✅ Wallbox returned to Available state")
        except asyncio.TimeoutError:
            logger.warning("   ⚠️  Timeout waiting for Available status")

        logger.info(f"--- Step B.4 for {self.charge_point_id} complete. ---")
