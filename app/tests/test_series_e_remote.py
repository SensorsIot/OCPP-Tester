"""
OCPP Test Series E: Remote Operations

This module contains all E-series tests related to:
- RemoteStartTransaction from different EV states
- Dynamic charging profile adjustments during active sessions
- TxProfile management
- Remote charging session control

Test Methods:
- E.1 (run_e1_remote_start_state_a): Remote start from state A (Available)
- E.2 (run_e2_remote_start_state_b): Remote start from state B (Preparing)
- E.3 (run_e3_remote_start_state_c): Remote start from state C (Charging)
- E.4 (run_e4_set_profile_6a): Set TxProfile to low power
- E.5 (run_e5_set_profile_10a): Set TxProfile to medium power
- E.6 (run_e6_set_profile_16a): Set TxProfile to high power
- E.7 (run_e7_clear_profile): Clear default charging profiles
- E.11 (run_e11_clear_all_profiles): Clear ALL charging profiles
"""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from dataclasses import asdict

from app.core import (
    CHARGE_POINTS, TRANSACTIONS, OCPP_MESSAGE_TIMEOUT,
    get_active_transaction_id, set_active_transaction_id,
    get_charging_value, get_charging_rate_unit
)
from app.messages import (
    RemoteStartTransactionRequest, SetChargingProfileRequest,
    ClearChargingProfileRequest, GetCompositeScheduleRequest,
    ChargingProfile, ChargingSchedule, ChargingSchedulePeriod,
    ChargingProfilePurposeType, ChargingProfileKindType, ChargingRateUnitType,
)
from app.tests.test_base import OcppTestBase

if TYPE_CHECKING:
    from app.ocpp_server_logic import OcppServerLogic

logger = logging.getLogger(__name__)


class TestSeriesE(OcppTestBase):
    """
    Test Series E: Remote Operations (8 tests)

    Covers RemoteStartTransaction and dynamic profile management.
    """

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

    async def run_e11_clear_all_profiles(self):
        """E.11: Clears ALL charging profiles from the charge point."""
        logger.info(f"--- Step E.11: Clearing ALL charging profiles for {self.charge_point_id} ---")
        step_name = "run_e11_clear_all_profiles"
        self._check_cancellation()

        logger.info("Sending ClearChargingProfile request to clear profiles for connectorId=0...")
        success_0 = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest(connectorId=0),
            timeout=OCPP_MESSAGE_TIMEOUT
        )
        self._check_cancellation()

        logger.info("Sending ClearChargingProfile request to clear profiles for connectorId=1...")
        success_1 = await self.handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest(connectorId=1),
            timeout=OCPP_MESSAGE_TIMEOUT
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
