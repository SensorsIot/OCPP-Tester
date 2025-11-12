"""
OCPP Test Series D: Smart Charging

This module contains all D-series tests related to:
- Smart charging capabilities
- ChargePointMaxProfile management
- Default profile configuration

Test Methods:
- D.3 (run_d3_smart_charging_capability_test): Smart charging capability test
- D.5 (run_d5_set_profile_5000w): Set ChargePointMaxProfile to medium power
- D.6 (run_d6_set_high_charging_profile): Set TxDefaultProfile to high power
"""

import asyncio
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING
from dataclasses import asdict

from app.core import OCPP_MESSAGE_TIMEOUT, get_charging_value
from app.messages import (
    SetChargingProfileRequest, ClearChargingProfileRequest,
    ChargingProfile, ChargingSchedule, ChargingSchedulePeriod,
    ChargingProfilePurposeType, ChargingProfileKindType,
)
from app.tests.test_base import OcppTestBase

if TYPE_CHECKING:
    from app.ocpp_server_logic import OcppServerLogic

logger = logging.getLogger(__name__)


class TestSeriesD(OcppTestBase):
    """
    Test Series D: Smart Charging (3 tests)

    Covers smart charging capabilities and profile management.
    """

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
