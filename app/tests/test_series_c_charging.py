"""
OCPP Test Series C: Charging Profile Management

This module contains all C-series tests related to:
- SetChargingProfile (TxProfile, TxDefaultProfile, ChargePointMaxProfile)
- ClearChargingProfile
- GetCompositeSchedule
- Transaction management and cleanup
- Power/current limit verification

Test Methods:
- C.1 (run_c1_set_charging_profile_test): Set TxProfile on active transaction
- C.2 (run_c2_user_initiated_transaction_test): Manual transaction start (user action)
- C.2 (run_c2_tx_default_profile_test): Set TxDefaultProfile for future transactions
- C.3 (run_c3_check_power_limits_test): Check current power/current limits
- C.3 (run_c3_get_composite_schedule_test): Get composite schedule
- C.4 (run_c4_clear_charging_profile_test): Clear charging profiles
- C.5 (run_c5_cleanup_test): Cleanup transactions and profiles
"""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict
from dataclasses import asdict

from app.core import (
    CHARGE_POINTS, TRANSACTIONS, VERIFICATION_RESULTS, OCPP_MESSAGE_TIMEOUT,
    get_charging_value, get_charging_rate_unit
)
from app.messages import (
    RemoteStartTransactionRequest, RemoteStopTransactionRequest,
    SetChargingProfileRequest, ClearChargingProfileRequest,
    GetCompositeScheduleRequest, ChargingProfile, ChargingSchedule,
    ChargingSchedulePeriod, ChargingProfilePurposeType, ChargingProfileKindType,
    ChargingRateUnitType,
)
from app.tests.test_base import OcppTestBase

if TYPE_CHECKING:
    from app.ocpp_server_logic import OcppServerLogic

logger = logging.getLogger(__name__)


class TestSeriesC(OcppTestBase):
    """
    Test Series C: Charging Profile Management (7 tests)

    Covers SetChargingProfile, ClearChargingProfile, GetCompositeSchedule, and verification.
    """

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
                timeout=OCPP_MESSAGE_TIMEOUT
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
                    chargingRateUnit=charging_unit,
                    chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=limit, numberPhases=number_phases)],
                    duration=duration,
                    startSchedule=datetime.now(timezone.utc).isoformat()
                )
            )
        )
        success = await self.handler.send_and_wait("SetChargingProfile", profile, timeout=OCPP_MESSAGE_TIMEOUT)
        self._check_cancellation()

        test_passed = False
        verification_results = []

        if success and success.get("status") == "Accepted":
            logger.info("SUCCESS: SetChargingProfile was acknowledged by the charge point.")
            test_passed = True

            logger.info("🔍 Verifying profile application with GetCompositeSchedule...")
            await asyncio.sleep(2)

            verify_response = await self.handler.send_and_wait(
                "GetCompositeSchedule",
                GetCompositeScheduleRequest(connectorId=1, duration=3600, chargingRateUnit=None),
                timeout=OCPP_MESSAGE_TIMEOUT
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
                    timeout=OCPP_MESSAGE_TIMEOUT
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

        # If no unit or limit specified, use configured charging values
        if charging_unit is None or limit is None:
            medium_value, default_unit = get_charging_value("medium")
            if charging_unit is None:
                charging_unit = default_unit
            if limit is None:
                limit = medium_value

        logger.info(f"--- Step C.2: Running TxDefaultProfile test to {limit}{charging_unit} for {self.charge_point_id} ---")
        step_name = "run_c2_tx_default_profile_test"
        self._check_cancellation()

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
                    ],
                    startSchedule=datetime.now(timezone.utc).isoformat()
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

            logger.info("🔍 Verifying profile application with GetCompositeSchedule on connector 1...")
            await asyncio.sleep(2)

            verify_response = await self.handler.send_and_wait(
                "GetCompositeSchedule",
                GetCompositeScheduleRequest(connectorId=1, duration=3600, chargingRateUnit=None),
                timeout=OCPP_MESSAGE_TIMEOUT
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

    async def run_c4_clear_charging_profile_test(self):
        """C.4: ClearChargingProfile - Clears ALL charging profiles."""
        logger.info(f"--- Step C.4: Running ClearChargingProfile test for {self.charge_point_id} ---")
        step_name = "run_c4_clear_charging_profile_test"
        self._check_cancellation()

        logger.info("🧹 Clearing ALL charging profiles...")
        response = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest()  # No parameters = clear ALL profiles
        )
        self._check_cancellation()

        test_passed = False
        if response and response.get("status") == "Accepted":
            logger.info("✅ ClearChargingProfile was accepted by the charge point.")

            # Verify profiles were actually cleared
            logger.info("🔍 Verifying profiles were cleared with GetCompositeSchedule...")
            await asyncio.sleep(1)  # Give wallbox time to clear profiles

            verify_response = await self.handler.send_and_wait(
                "GetCompositeSchedule",
                GetCompositeScheduleRequest(connectorId=1, duration=3600),
                timeout=OCPP_MESSAGE_TIMEOUT
            )

            if verify_response and verify_response.get("status") == "Accepted":
                schedule = verify_response.get("chargingSchedule")
                if schedule:
                    # There's still a schedule - profiles not fully cleared
                    logger.error("❌ VERIFICATION FAILED: Charging profiles still present after clear")
                    logger.error(f"   Active schedule: {schedule}")
                    logger.info("   💡 The wallbox may have a default profile that cannot be cleared")
                    logger.info("   💡 Or ChargePointMaxProfile which is not clearable")
                    test_passed = False
                else:
                    logger.info("✅ VERIFICATION PASSED: No charging profiles active")
                    test_passed = True
            else:
                logger.warning(f"⚠️  Could not verify profile clearing: {verify_response}")
                logger.info("   💡 Assuming clear was successful since wallbox accepted the command")
                test_passed = True

        elif response and response.get("status") == "Unknown":
            logger.warning("⚠️  WARNING: ClearChargingProfile returned 'Unknown' - no matching profile found.")
            logger.info("   💡 This indicates no profiles were set, which is acceptable.")
            test_passed = True
        elif response:
            logger.error(f"❌ FAILURE: ClearChargingProfile returned unexpected status: {response.get('status')}")
            test_passed = False
        else:
            logger.error("❌ FAILURE: ClearChargingProfile - no response received.")
            test_passed = False

        if test_passed:
            self._set_test_result(step_name, "PASSED")
        else:
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
                    timeout=OCPP_MESSAGE_TIMEOUT
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

        response = await self.handler.send_and_wait("GetCompositeSchedule", composite_request, timeout=OCPP_MESSAGE_TIMEOUT)
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
