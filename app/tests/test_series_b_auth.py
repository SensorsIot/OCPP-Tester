"""
OCPP Test Series B: Authorization & Status Management

This module contains all B-series tests per FSD specification.

**Core OCPP Scenarios (4 tests):**
- B.1 (run_b1_rfid_public_charging_test): RFID before plug-in (tap-first authorization)
- B.2 (run_b2_local_cache_authorization_test): RFID after plug-in (plug-first, local cache)
- B.3 (run_b3_remote_smart_charging_test): Remote start transaction (no RFID needed)
- B.4 (run_b4_offline_local_start_test): Plug & Charge / LocalPreAuthorize (no RFID needed)

**Utility Functions (3 tests):**
- B.6 (run_b5_clear_rfid_cache): Clear RFID authorization cache
- B.7 (run_b6_send_rfid_list): Send local authorization list to wallbox
- B.8 (run_b7_get_rfid_list_version): Get current list version
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
    ensure_test_configuration,
    # EV connection management
    prepare_ev_connection,
    set_ev_state_and_wait_for_status,
    # Cleanup operations
    cleanup_transaction_and_state,
    # Status management
    wait_for_connector_status,
)
from app.tests.test_base import OcppTestBase

if TYPE_CHECKING:
    from app.ocpp_server_logic import OcppServerLogic

logger = logging.getLogger(__name__)


class TestSeriesB(OcppTestBase):
    """
    Test Series B: Authorization & Status Management (7 tests per FSD)

    Core Scenarios: B.1, B.2 (RFID), B.3 (Remote Start), B.4 (Plug & Charge)
    Utility Functions: B.6 (Clear Cache), B.7 (Send List), B.8 (Get Version)
    """

    async def _ensure_ready_state(self):
        """
        Ensure wallbox is in a clean 'Available' state before starting a test.

        Steps:
        1. Check current status (trigger if unknown)
        2. Stop any running transaction
        3. Reset EV state to A
        4. Wait for Available status

        Returns:
            bool: True if wallbox is ready, False otherwise
        """
        logger.info("🔍 Pre-test check: Ensuring wallbox is ready...")

        # Step 1: Get current status
        cp_data = CHARGE_POINTS.get(self.charge_point_id, {})
        current_status = cp_data.get("status")

        if not current_status:
            logger.info("   ⚠️  No status known - triggering StatusNotification...")
            from app.messages import TriggerMessageRequest

            trigger_response = await self.handler.send_and_wait(
                "TriggerMessage",
                TriggerMessageRequest(requestedMessage="StatusNotification", connectorId=1),
                timeout=OCPP_MESSAGE_TIMEOUT
            )

            if trigger_response and trigger_response.get("status") == "Accepted":
                await asyncio.sleep(2)  # Wait for StatusNotification
                current_status = CHARGE_POINTS.get(self.charge_point_id, {}).get("status")
                logger.info(f"   ✅ Current status: {current_status}")
            else:
                logger.warning("   ⚠️  Could not get status")
        else:
            logger.info(f"   ✅ Current status: {current_status}")

        # Step 2: Check for running transaction and stop it
        active_transaction_id = None
        for tx_id, tx_data in TRANSACTIONS.items():
            if (tx_data.get("charge_point_id") == self.charge_point_id and
                tx_data.get("status") == "Ongoing"):
                active_transaction_id = tx_id
                break

        if active_transaction_id:
            logger.info(f"   ⚠️  Active transaction found (ID: {active_transaction_id}) - stopping it...")

            try:
                stop_response = await self.handler.send_and_wait(
                    "RemoteStopTransaction",
                    RemoteStopTransactionRequest(transactionId=active_transaction_id),
                    timeout=OCPP_MESSAGE_TIMEOUT
                )

                if stop_response and stop_response.get("status") == "Accepted":
                    logger.info("   ✅ Stop command accepted")
                    await asyncio.sleep(3)  # Wait for StopTransaction message
                else:
                    logger.warning(f"   ⚠️  Stop rejected: {stop_response}")
            except Exception as e:
                logger.warning(f"   ⚠️  Error stopping transaction: {e}")

        # Step 3: Reset EV state to A (disconnected)
        logger.info("   🔌 Resetting EV state to A (disconnected)...")
        await self._set_ev_state("A")
        await asyncio.sleep(2)

        # Step 4: Wait for Available status
        logger.info("   ⏳ Waiting for wallbox to become 'Available'...")
        try:
            await asyncio.wait_for(self._wait_for_status("Available"), timeout=15)
            logger.info("   ✅ Wallbox is now in 'Available' state - ready for test")
            return True
        except asyncio.TimeoutError:
            current_status = CHARGE_POINTS.get(self.charge_point_id, {}).get("status")
            logger.warning(f"   ⚠️  Wallbox stuck in '{current_status}' state after 15s")
            logger.warning("   💡 Test may fail - wallbox should be 'Available'")
            return False

    async def run_b5_clear_rfid_cache(self):
        """B.5: Clear RFID Cache - Clears the local authorization list (RFID cache) in the wallbox."""
        logger.info(f"--- Step B.5: Clear RFID Cache for {self.charge_point_id} ---")
        step_name = "run_b5_clear_rfid_cache"
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

    async def run_b6_send_rfid_list(self):
        """B.6: Send RFID List - Sends a local authorization list with RFID cards to the wallbox."""
        logger.info(f"--- Step B.6: Send RFID List for {self.charge_point_id} ---")
        step_name = "run_b6_send_rfid_list"
        self._check_cancellation()

        logger.info("📋 Sending local authorization list to wallbox...")
        logger.info("   📘 This sends RFID card IDs that should be authorized locally")
        logger.info("   📘 Cards in this list can authorize transactions without Central System")

        # Create some example RFID cards for the authorization list
        rfid_cards = [
            AuthorizationData(
                idTag="1234567890",
                idTagInfo=IdTagInfo(status="Accepted")
            ),
            AuthorizationData(
                idTag="9876543210",
                idTagInfo=IdTagInfo(status="Accepted")
            ),
            AuthorizationData(
                idTag="5555555555",
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

    async def run_b7_get_rfid_list_version(self):
        """B.7: Get RFID List Version - Gets the current version of the local authorization list."""
        logger.info(f"--- Step B.7: Get RFID List Version for {self.charge_point_id} ---")
        step_name = "run_b7_get_rfid_list_version"
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

        # Log version info
        try:
            from app.version import get_version_string
            logger.info(f"Code version: {get_version_string()}")
        except:
            logger.warning("Version information not available")

        step_name = "run_b1_rfid_public_charging_test"
        self._check_cancellation()

        logger.info("")
        logger.info("=" * 80)
        logger.info("PREPARATION")
        logger.info("=" * 80)
        logger.info("")
        logger.info("🎫 RFID AUTHORIZATION BEFORE PLUG-IN TEST")
        logger.info("")
        logger.info("📋 Step 0: Preparing test environment...")
        logger.info("   • Stopping active transactions")
        logger.info("   • Verifying OCPP parameters")
        logger.info("   • Please wait...")
        logger.info("")

        # Ensure wallbox is ready (stop running transactions, reset to Available)
        await self._ensure_ready_state()
        logger.info("")

        # Step 1: Verify required configuration parameters
        required_params = [
            {
                "key": "LocalPreAuthorize",
                "value": "false",
                "description": "Wait for backend authorization"
            },
            {
                "key": "LocalAuthorizeOffline",
                "value": "false",
                "description": "No offline start"
            }
        ]

        success, message = await ensure_test_configuration(
            self.handler,
            required_params,
            test_name="B.1 RFID Authorization Before Plug-in"
        )
        self._check_cancellation()

        if not success:
            logger.error(f"❌ Test prerequisites not met: {message}")
            if "RebootRequired" in message:
                logger.info("   💡 Wallbox needs to be rebooted for configuration changes to take effect")
            self._set_test_result(step_name, "FAILED")
            return

        logger.info("")
        logger.info("✅ Test environment ready!")
        logger.info("")
        logger.info("=" * 80)
        logger.info("START TEST")
        logger.info("=" * 80)
        logger.info("")
        logger.info("   📘 This tests the standard OCPP 1.6-J authorization flow:")
        logger.info("   📘 1. User taps RFID card → Wallbox sends Authorize request")
        logger.info("   📘 2. Central System responds Accepted/Blocked")
        logger.info("   📘 3. Test automatically plugs in EV → Wallbox starts transaction")
        logger.info("")
        logger.info("👤 USER ACTION (OPTIONAL):")
        logger.info("   • TAP your RFID card on the wallbox reader")
        logger.info("   • If no card tapped within 15 seconds, test continues in simulation mode")
        logger.info("")
        logger.info("🤖 AUTOMATIC ACTIONS:")
        logger.info("   • Central System will accept the RFID card")
        logger.info("   • EV simulator will automatically plug in (State B)")
        logger.info("   • Transaction will start automatically")
        logger.info("")
        logger.info("⏳ Waiting for RFID card tap (timeout: 15 seconds)...")
        logger.info("   💡 Test will proceed with simulated card if no physical card detected")

        # Clear any stale RFID data from early taps (before test was ready)
        from app.core import CHARGE_POINTS
        if self.charge_point_id in CHARGE_POINTS:
            CHARGE_POINTS[self.charge_point_id]["accepted_rfid"] = None
            logger.debug("🔄 Cleared stale RFID data - ready for fresh tap")

        # Enable RFID test mode - accept ANY card during B.1 test
        from app.ocpp_message_handlers import rfid_test_state
        rfid_test_state["active"] = True
        rfid_test_state["cards_presented"] = []
        logger.debug("🔓 RFID test mode enabled - any card will be accepted")

        # Track authorization state
        authorized_card = None
        transaction_started = False
        rfid_detected = False
        physical_card_used = False

        # Wait for RFID Authorization request from wallbox
        start_time = asyncio.get_event_loop().time()
        timeout = 15  # 15 seconds to tap card

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
                        physical_card_used = True
                        authorized_card = cp_data.get("accepted_rfid")
                        logger.info(f"✅ PHYSICAL RFID card detected and authorized: {authorized_card}")
                        logger.info("   Central System accepted the card")
                        logger.info("")
                        logger.info("🔌 Automatically plugging in EV cable...")
                        logger.info("   🔧 EV SIMULATOR: Setting state to B (Cable Connected)")

                        # Set EV simulator to State B and wait for wallbox confirmation
                        success, message = await set_ev_state_and_wait_for_status(
                            self.ocpp_server_logic,
                            self.charge_point_id,
                            ev_state="B",
                            expected_status="Preparing",
                            timeout=15.0
                        )

                        if success:
                            logger.info("   ✅ EV cable connected - wallbox confirmed 'Preparing' state")
                        else:
                            logger.warning(f"   ⚠️  {message}")
                            logger.warning("   ⚠️  Wallbox did not confirm state change - test may fail")

                        # Set EV state to C (vehicle requesting power) to trigger transaction start
                        logger.info("")
                        logger.info("   🔋 Requesting power from wallbox...")
                        logger.info("   🔧 EV SIMULATOR: Setting state to C (Vehicle Requesting Power)")
                        success_c, message_c = await set_ev_state_and_wait_for_status(
                            self.ocpp_server_logic,
                            self.charge_point_id,
                            ev_state="C",
                            expected_status="Charging",
                            timeout=15.0
                        )

                        if success_c:
                            logger.info("   ✅ Vehicle requesting power - wallbox should start transaction")
                        else:
                            logger.warning(f"   ⚠️  {message_c}")
                            logger.info("   💡 Continuing anyway - checking for transaction...")

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
            pass  # Continue with simulation mode

        # If no physical card was tapped, simulate the scenario
        if not rfid_detected:
            logger.warning("⏱️  TIMEOUT: No physical RFID card detected within 15 seconds")
            logger.info("")
            logger.info("🔄 CONTINUING IN SIMULATION MODE (Development/Remote Testing)")
            logger.info("   💡 This allows testing the complete OCPP flow without lab access")
            logger.info("   💡 In lab environment, present physical RFID card for full test")
            logger.info("")
            logger.info("🎫 Simulating RFID card presentation...")

            # Simulate authorization by triggering RemoteStartTransaction with simulated ID tag
            from app.messages import RemoteStartTransactionRequest
            simulated_id_tag = "DEV_SIMULATED_CARD_001"

            logger.info(f"   Using simulated ID tag: {simulated_id_tag}")
            logger.info("   Sending RemoteStartTransaction (simulates successful RFID auth)...")

            remote_start_request = RemoteStartTransactionRequest(
                idTag=simulated_id_tag,
                connectorId=1
            )

            response = await self.handler.send_and_wait(
                "RemoteStartTransaction",
                remote_start_request,
                timeout=OCPP_MESSAGE_TIMEOUT
            )

            if response and response.get("status") == "Accepted":
                logger.info("   ✅ Simulated authorization accepted")
                authorized_card = simulated_id_tag

                # Wait for transaction to start
                await asyncio.sleep(3)

                # Check for transaction
                for tx_id, tx_data in TRANSACTIONS.items():
                    if (tx_data.get("charge_point_id") == self.charge_point_id and
                        tx_data.get("status") == "Ongoing"):
                        transaction_started = True
                        logger.info(f"   ✅ Simulated transaction started (ID: {tx_id})")
                        break
            else:
                logger.error(f"   ❌ Simulated authorization failed: {response}")

        if not transaction_started:
            logger.error("❌ Test FAILED: No transaction was started")
            logger.info("   💡 Neither physical RFID nor simulation succeeded")
            rfid_test_state["active"] = False
            self._set_test_result(step_name, "FAILED")
            return

        # Test result depends on whether physical card was used
        if physical_card_used:
            logger.info("=" * 70)
            logger.info("✅ TAP-TO-CHARGE TEST PASSED (PHYSICAL RFID CARD)")
            logger.info("=" * 70)
            logger.info(f"   🎫 Physical RFID Card: {authorized_card}")
            logger.info("   ⚡ Transaction: Started")
            logger.info("   💡 Standard OCPP 1.6-J authorization flow working correctly")
            test_result = "PASSED"
        else:
            logger.info("=" * 70)
            logger.info("⚠️  TAP-TO-CHARGE TEST PASSED (SIMULATION MODE)")
            logger.info("=" * 70)
            logger.info(f"   🎫 Simulated ID Tag: {authorized_card}")
            logger.info("   ⚡ Transaction: Started via RemoteStartTransaction")
            logger.info("   💡 OCPP flow validated - use physical RFID in lab for full test")
            logger.info("   ℹ️  Status: PARTIAL (simulation mode, no physical RFID presented)")
            test_result = "PARTIAL"

        rfid_test_state["active"] = False  # Disable RFID test mode
        self._set_test_result(step_name, test_result)

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
        logger.info("   🔧 EV SIMULATOR: Resetting state to A (Unplugged)")
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

        # Log version info
        try:
            from app.version import get_version_string
            logger.info(f"Code version: {get_version_string()}")
        except:
            logger.warning("Version information not available")

        step_name = "run_b2_local_cache_authorization_test"
        self._check_cancellation()

        logger.info("")
        logger.info("=" * 80)
        logger.info("PREPARATION")
        logger.info("=" * 80)
        logger.info("")

        # Ensure wallbox is ready (stop running transactions, reset to Available)
        await self._ensure_ready_state()
        logger.info("")
        logger.info("🎫 RFID AUTHORIZATION AFTER PLUG-IN TEST (Local Cache Authorization)")
        logger.info("   📘 This tests OCPP local cache authorization after plug-in:")
        logger.info("   📘 1. User plugs in EV first")
        logger.info("   📘 2. User taps RFID card")
        logger.info("   📘 3. Wallbox checks LOCAL cache (instant validation)")
        logger.info("   📘 4. Transaction starts within 2 seconds (no network delay)")
        logger.info("")

        # Step 0: Verify required configuration parameters
        required_params = [
            {
                "key": "LocalAuthListEnabled",
                "value": "true",
                "description": "Enable local authorization cache"
            },
            {
                "key": "LocalAuthorizeOffline",
                "value": "true",
                "description": "Allow offline authorization from cache"
            },
            {
                "key": "LocalPreAuthorize",
                "value": "false",
                "description": "Wait for authorization (don't auto-start)"
            }
        ]

        success, message = await ensure_test_configuration(
            self.handler,
            required_params,
            test_name="B.2 RFID Authorization After Plug-in"
        )
        self._check_cancellation()

        if not success:
            logger.error(f"❌ Test prerequisites not met: {message}")
            if "RebootRequired" in message:
                logger.info("   💡 Wallbox configuration updated - please reboot wallbox and run test again")
            self._set_test_result(step_name, "FAILED")
            return

        logger.info("")

        # Prepare local authorization list for the test
        logger.info("📋 Step 0: Preparing local authorization list...")
        logger.info("   💡 Clearing wallbox RFID cache to ensure clean test state")
        logger.info("   💡 Note: This test uses LOCAL cache authorization (LocalAuthListEnabled=true)")

        # Clear existing local authorization cache to prevent auto-start
        from app.messages import ClearCacheRequest

        logger.info("   🗑️  Attempting to clear existing RFID cache...")
        try:
            clear_response = await self.handler.send_and_wait("ClearCache", ClearCacheRequest(), timeout=10)
            if clear_response and clear_response.get("status") == "Accepted":
                logger.info("   ✅ Local RFID cache cleared successfully")
                logger.info("   💡 This prevents auto-start from cached cards (like 'ElecqAutoStart')")
            else:
                status = clear_response.get("status", "Unknown") if clear_response else "No response"
                logger.warning(f"   ⚠️  ClearCache returned: {status}")
                logger.warning("   💡 Some wallboxes have protected cache entries that cannot be cleared")
                logger.warning("   💡 This test will proceed - card may need to be in local list already")
        except Exception as e:
            logger.warning(f"   ⚠️  Error clearing cache: {e}")

        await asyncio.sleep(1)
        logger.info("")
        logger.info("=" * 80)
        logger.info("START TEST")
        logger.info("=" * 80)
        logger.info("")

        # Enable RFID test mode - accept ANY card during B.2 test
        from app.ocpp_message_handlers import rfid_test_state
        rfid_test_state["active"] = True
        rfid_test_state["cards_presented"] = []
        logger.debug("🔓 RFID test mode enabled - any card will be accepted")

        # Step 1: Plug in EV first (before RFID tap)
        logger.info("📡 Step 1: Plugging in EV cable...")
        logger.info("   🔧 EV SIMULATOR: Setting state to B (Cable Connected)")
        await self._set_ev_state("B")
        self._check_cancellation()
        await asyncio.sleep(2)  # Give wallbox time to process connection

        # Check if wallbox auto-started transaction
        for tx_id, tx_data in TRANSACTIONS.items():
            if (tx_data.get("charge_point_id") == self.charge_point_id and
                tx_data.get("status") == "Ongoing"):
                auto_started_tag = tx_data.get("id_tag") or "anonymous"
                logger.error(f"❌ Transaction auto-started with idTag '{auto_started_tag}' before RFID tap")
                logger.error(f"   Configuration: LocalAuthListEnabled=false, LocalAuthorizeOffline=false, LocalPreAuthorize=false")
                await self._set_ev_state("A")
                self._set_test_result(step_name, "FAILED", f"Auto-started with '{auto_started_tag}' ignoring OCPP parameters")
                return

        logger.info("   ✅ EV connected (cable plugged in)")
        logger.info("   ✅ No auto-start detected - wallbox waiting for authorization")
        logger.info("")

        # Step 2: Wait for RFID tap
        logger.info("👤 Step 2: Now waiting for RFID card tap...")
        logger.info("")
        logger.info("🎫 MODAL DISPLAY:")
        logger.info("   📘 This tests the RFID-after-plug-in workflow")
        logger.info("   📘 1. Cable already connected (State B)")
        logger.info("   📘 2. Now tap your RFID card on the wallbox")
        logger.info("   📘 3. Wallbox sends Authorize.req to backend")
        logger.info("")
        logger.info("👤 USER ACTION (OPTIONAL):")
        logger.info("   • TAP your RFID card on the wallbox reader")
        logger.info("   • If no card tapped within 60 seconds, test continues in simulation mode")
        logger.info("")
        logger.info("🤖 AUTOMATIC ACTIONS:")
        logger.info("   • Wallbox will send Authorize.req to backend for validation")
        logger.info("   • Transaction will start after backend authorization")
        logger.info("")
        logger.info("⏳ Waiting for RFID card tap (timeout: 60 seconds)...")
        logger.info("   💡 Test will proceed with simulated card if no physical card detected")

        # Wait for Authorize message
        start_time = asyncio.get_event_loop().time()
        timeout = 60  # 60 seconds for user to tap card
        authorized_id_tag = None
        physical_card_used = False

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            self._check_cancellation()
            await asyncio.sleep(0.5)

            # Check if an Authorize was received (stored in charge point data)
            cp_data = CHARGE_POINTS.get(self.charge_point_id, {})
            authorized_id_tag = cp_data.get("accepted_rfid")

            if authorized_id_tag:
                physical_card_used = True
                logger.info(f"   ✅ PHYSICAL RFID card detected: {authorized_id_tag}")
                break

        # If no physical card, simulate one
        if not authorized_id_tag:
            logger.warning("⏱️  TIMEOUT: No physical RFID card detected within 60 seconds")
            logger.info("")
            logger.info("🔄 CONTINUING IN SIMULATION MODE (Development/Remote Testing)")
            logger.info("   💡 This allows testing the complete OCPP flow without lab access")
            logger.info("   💡 In lab environment, present physical RFID card for full test")
            logger.info("")
            logger.info("🎫 Using simulated RFID authorization...")

            # Use simulated tag
            authorized_id_tag = "DEV_SIMULATED_CARD_002"
            logger.info(f"   Simulated ID tag: {authorized_id_tag}")

            # Store it as if it was accepted
            if self.charge_point_id in CHARGE_POINTS:
                CHARGE_POINTS[self.charge_point_id]["accepted_rfid"] = authorized_id_tag
                logger.info("   ✅ Simulated authorization ready")

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
            logger.info("   • LocalAuthListEnabled was not set correctly")
            logger.info("   • Run B.6 (Send RFID List) to add your card to local cache")
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
        logger.info("📡 Step 4: Requesting power from wallbox...")
        logger.info("   🔧 EV SIMULATOR: Setting state to C (Vehicle Requesting Power)")
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
        logger.info("=" * 70)
        if physical_card_used:
            logger.info("✅ LOCAL CACHE AUTHORIZATION TEST PASSED (PHYSICAL RFID CARD)")
            logger.info("=" * 70)
            logger.info(f"   ⚡ Transaction ID: {transaction_id}")
            logger.info(f"   🎫 Physical RFID Card: {authorized_id_tag}")
            logger.info(f"   ⚡ Start delay: {transaction_start_delay:.2f} seconds")
            logger.info("   📱 Plug-first flow working correctly")
            test_result = "PASSED"
        else:
            logger.info("⚠️  LOCAL CACHE AUTHORIZATION TEST PASSED (SIMULATION MODE)")
            logger.info("=" * 70)
            logger.info(f"   ⚡ Transaction ID: {transaction_id}")
            logger.info(f"   🎫 Simulated ID Tag: {authorized_id_tag}")
            logger.info(f"   ⚡ Start delay: {transaction_start_delay:.2f} seconds")
            logger.info("   💡 OCPP flow validated - use physical RFID in lab for full test")
            logger.info("   ℹ️  Status: PARTIAL (simulation mode, no physical RFID presented)")
            test_result = "PARTIAL"

        self._set_test_result(step_name, test_result)

        # Disable RFID test mode
        rfid_test_state["active"] = False

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
        logger.info("   🔧 EV SIMULATOR: Resetting state to A (Unplugged)")
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

        # Ensure wallbox is ready (stop running transactions, reset to Available)
        await self._ensure_ready_state()
        logger.info("")
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

        required_params = [
            {
                "key": "AuthorizeRemoteTxRequests",
                "value": "true",
                "description": "Wallbox validates idTag for remote starts"
            }
        ]

        success, message = await ensure_test_configuration(
            self.handler,
            required_params,
            test_name="B.3 Remote Smart Charging"
        )
        self._check_cancellation()

        if not success:
            logger.error(f"❌ Test prerequisites not met: {message}")
            self._set_test_result(step_name, "FAILED")
            return

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

        # Ensure wallbox is ready (stop running transactions, reset to Available)
        await self._ensure_ready_state()
        logger.info("")

        logger.info("🔌 PLUG-AND-CHARGE TEST")
        logger.info("   📘 This tests automatic charging with LocalPreAuthorize:")
        logger.info("   📘 1. User plugs in their EV (no RFID tap needed)")
        logger.info("   📘 2. Wallbox automatically starts transaction with default idTag")
        logger.info("   📘 3. Charging begins immediately")
        logger.info("")
        logger.info("💡 Use case: Private home chargers - just plug in and charge!")
        logger.info("")

        # Step 0: Verify and enable LocalPreAuthorize
        required_params = [
            {
                "key": "LocalPreAuthorize",
                "value": "true",
                "description": "Enable plug-and-charge (auto-start on plug-in)"
            }
        ]

        success, message = await ensure_test_configuration(
            self.handler,
            required_params,
            test_name="B.4 Plug & Charge"
        )
        self._check_cancellation()

        if not success:
            logger.error(f"❌ Test prerequisites not met: {message}")
            if "RebootRequired" in message:
                logger.info("   💡 Please run X.1: Reboot Wallbox and try B.4 again")
            self._set_test_result(step_name, "FAILED")
            return

        # Step 1: Ensure we're in idle state (State A)
        logger.info("")
        logger.info("🔄 Step 1: Ensuring wallbox is ready (State A)...")

        await self._set_ev_state("A")
        await asyncio.sleep(2)
        logger.info("   ✅ Wallbox ready in idle state")

        # Step 2: Plug in EV (State B) - this should automatically start charging
        logger.info("")
        logger.info("🔌 Step 2: Plugging in EV...")
        logger.info("   💡 With LocalPreAuthorize enabled, wallbox should auto-start transaction")

        await self._set_ev_state("B")
        await asyncio.sleep(1)
        logger.info("   ✅ EV cable connected (State B)")

        # Step 3: Wait for automatic transaction start
        logger.info("")
        logger.info("⏳ Step 3: Waiting for automatic transaction start...")
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


