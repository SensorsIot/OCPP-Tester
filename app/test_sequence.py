import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.messages import (
    ChangeAvailabilityRequest, ChangeConfigurationRequest, TriggerMessageRequest,
    GetConfigurationRequest, RemoteStartTransactionRequest, RemoteStopTransactionRequest,
    ChargingProfile, ChargingSchedule, ChargingSchedulePeriod,
    ChargingProfilePurposeType, ChargingProfileKindType, ChargingRateUnitType,
    GetCompositeScheduleRequest, ClearChargingProfileRequest
)
from app.core import TRANSACTIONS, CHARGE_POINTS, EV_SIMULATOR_BASE_URL, SERVER_SETTINGS

if TYPE_CHECKING:
    from app.ocpp_server_logic import OcppServerLogic

logger = logging.getLogger(__name__)

class TestSequence:
    def __init__(self, ocpp_logic: "OcppServerLogic"):
        self.ocpp_logic = ocpp_logic
        self.charge_point_id = ocpp_logic.charge_point_id

    async def run_full_sequence(self):
        logger.info(f"========================STARTING FULL TEST SEQUENCE FOR {self.charge_point_id}==========================")

        # A: Core Communication & Status
        await self.ocpp_logic.test_steps.run_a1_change_configuration_test()
        await self.ocpp_logic.test_steps.run_a2_get_configuration_test()

        # B: Authorization & Transaction Management
        await self.ocpp_logic.test_steps.run_b1_remote_start_transaction_test()
        await self.ocpp_logic.test_steps.run_b2_remote_stop_transaction_test()

        # C: Smart Charging Profile
        await self.ocpp_logic.test_steps.run_c1_set_charging_profile_test()
        await self.ocpp_logic.test_steps.run_c2_get_composite_schedule_test()
        await self.ocpp_logic.test_steps.run_c3_clear_charging_profile_test()
        await self.ocpp_logic.test_steps.run_c4_tx_default_profile_test()

        logger.info(f"Full test sequence for {self.charge_point_id} complete.")
        logger.info("========================END OF TEST SEQUENCE===============================")

    async def step_a1_initial_registration(self):
        logger.info("\n\n\n\n\n--- Step A.1: Initial Connection and Registration ---")
        request = ChangeAvailabilityRequest(connectorId=0, type="Operative")
        await self.ocpp_logic.send_and_wait("ChangeAvailability", request)

    async def step_a2_configuration_exchange(self):
        logger.info("\n\n\n\n\n--- Step A.2: Configuration Exchange ---")
        # First, read the current state of the charge point for logging and diagnostics.
        await self.ocpp_logic.send_and_wait("GetConfiguration", GetConfigurationRequest())
        # Trigger a boot notification to ensure the charge point is fully registered.
        # This may be rejected if the charge point is already booted, which is acceptable.
        await self.ocpp_logic.send_and_wait("TriggerMessage", TriggerMessageRequest(requestedMessage="BootNotification"))

        # Enforce a Desired State: This guarantees that, regardless of the charge
        # point's previous settings, it will now behave in a predictable way
        # (e.g., it will send the specific meter values the server wants to see).

        # Configure meter values to ensure the charge point sends the data we need.
        # We set the full list of desired measurands in a single command for efficiency.
        meter_values_to_sample = [
            "Power.Active.Import", "Energy.Active.Import.Register", "Current.Import",
            "Voltage", "Current.Offered", "Power.Offered", "SoC"
        ]
        request = ChangeConfigurationRequest(key="MeterValuesSampledData", value=",".join(meter_values_to_sample))
        await self.ocpp_logic.send_and_wait("ChangeConfiguration", request)

        await self.ocpp_logic.send_and_wait("ChangeConfiguration", ChangeConfigurationRequest(key="MeterValueSampleInterval", value="10"))
        await self.ocpp_logic.send_and_wait("ChangeConfiguration", ChangeConfigurationRequest(key="WebSocketPingInterval", value="60"))
    
    async def step_c1_remote_transaction_test(self):
        logger.info("\n\n\n\n\n--- Step C.1: Remote Transaction Test ---")

        # To test a remote start, emulate the physical connection of an EV.
        await self.ocpp_logic._set_ev_state("B")
        await asyncio.sleep(2) # Give a moment for CP to process state B

        logger.info("Attempting to remotely start a transaction for idTag 'test_id_2' on connector 1.")
        request = RemoteStartTransactionRequest(idTag="test_id_2", connectorId=1)
        await self.ocpp_logic.send_and_wait("RemoteStartTransaction", request)

        # Emulate the EV starting to draw power, which is required for a transaction to start.
        await self.ocpp_logic._set_ev_state("C")
        logger.info("Waiting 30 seconds for the charge point to send a StartTransaction.req...")
        await asyncio.sleep(30)

        active_transaction_id = None
        for t_id, t_data in TRANSACTIONS.items():
            if (
                t_data.get("charge_point_id") == self.charge_point_id and
                t_data.get("id_tag") == "test_id_2" and "stop_time" not in t_data
            ):
                active_transaction_id = t_id
                break

        if active_transaction_id:
            logger.info(f"SUCCESS: Detected active transaction {active_transaction_id}.")
            await asyncio.sleep(15)
            logger.info(f"Attempting to remotely stop transaction {active_transaction_id}.")
            await self.ocpp_logic.send_and_wait("RemoteStopTransaction", RemoteStopTransactionRequest(transactionId=active_transaction_id))
            # Emulate the EV stopping the charge but remaining connected.
            await self.ocpp_logic._set_ev_state("B")
        else:
            logger.warning("NOTICE: No new transaction for 'test_id_2' was detected. Skipping remote stop.")

        # Clean up by simulating EV disconnection.
        await asyncio.sleep(5)
        await self.ocpp_logic._set_ev_state("A")

    async def step_c2_user_initiated_transaction_test(self):
        logger.info("\n\n\n\n\n--- Step C.2: User-Initiated Transaction Test ---")
        # To perform this test, the EV must be connected to allow the wallbox
        # to receive an Authorize.req and a StartTransaction.req.
        await self.ocpp_logic._set_ev_state("B")
        logger.info("ACTION REQUIRED: Present a valid ID tag to the physical charge point.")
        await asyncio.sleep(60)
        
        active_transaction = any(t.get("charge_point_id") == self.charge_point_id and "stop_time" not in t for t in TRANSACTIONS.values())
        if active_transaction:
            logger.info("SUCCESS: An active transaction was detected for this charge point.")
        else:
            logger.warning("NOTICE: No new transaction was detected.")

        # Clean up by simulating EV disconnection.
        await asyncio.sleep(5)
        await self.ocpp_logic._set_ev_state("A")

    async def step_a6_status_and_meter_value_acquisition(self):
        logger.info("\n\n\n\n\n--- Step A.6: Status and Meter Value Acquisition ---")
        await self.ocpp_logic.send_and_wait("TriggerMessage", TriggerMessageRequest(requestedMessage="StatusNotification", connectorId=1))
        await self.ocpp_logic.send_and_wait("TriggerMessage", TriggerMessageRequest(requestedMessage="MeterValues", connectorId=1))

    async def step_d3_smart_charging_capability_test(self):
        logger.info("\n\n\n\n\n--- Step D.3: Smart Charging Capability Test ---")
        # To make this test meaningful, we first set a known profile,
        # then immediately ask the charge point to report on the resulting schedule.
        logger.info("Setting a temporary default profile to verify composite schedule...")
        await self.step_d2_set_default_charging_profile()
        await self.ocpp_logic.send_and_wait("GetCompositeSchedule", GetCompositeScheduleRequest(connectorId=1, duration=60, chargingRateUnit="W"))
        logger.info("Cleaning up temporary profile...")
        await self.step_d4_clear_default_charging_profile()

    async def step_d1_set_live_charging_power(self):
        logger.info("\n\n\n\n\n--- Step D.1: Set Charging Power (for Active Transaction) ---")
        active_transaction = any(t.get("charge_point_id") == self.charge_point_id and "stop_time" not in t for t in TRANSACTIONS.values())
        if active_transaction:
            logger.info(f"Active transaction found. Setting charging profile (TxProfile).")
            profile = ChargingProfile(
                chargingProfileId=random.randint(1, 100),
                stackLevel=0,
                chargingProfilePurpose=ChargingProfilePurposeType.TxProfile,
                chargingProfileKind=ChargingProfileKindType.Absolute,
                chargingSchedule=ChargingSchedule(
                    chargingRateUnit=ChargingRateUnitType.W,
                    duration=60,
                    chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=5000)]
                )
            )
            await self.ocpp_logic.send_and_wait("SetChargingProfile", SetChargingProfileRequest(connectorId=1, csChargingProfiles=profile))
        else:
            logger.warning("No active transaction. Skipping SetChargingProfile with TxProfile.")

    async def step_d2_set_default_charging_profile(self):
        logger.info("\n\n\n\n\n--- Step D.2: Set Default Charging Profile ---")
        profile = ChargingProfile(
            chargingProfileId=random.randint(1, 100),
            stackLevel=0,
            chargingProfilePurpose=ChargingProfilePurposeType.TxDefaultProfile,
            chargingProfileKind=ChargingProfileKindType.Absolute,
            chargingSchedule=ChargingSchedule(
                chargingRateUnit=ChargingRateUnitType.W,
                duration=3600,
                chargingSchedulePeriod=[ChargingSchedulePeriod(startPeriod=0, limit=7000)]
            )
        )
        await self.ocpp_logic.send_and_wait("SetChargingProfile", SetChargingProfileRequest(connectorId=1, csChargingProfiles=profile))

    async def step_d4_clear_default_charging_profile(self):
        logger.info("\n\n\n\n\n--- Step D.4: Clear Default Charging Profile ---")
        request = ClearChargingProfileRequest(connectorId=1, chargingProfilePurpose=ChargingProfilePurposeType.TxDefaultProfile)
        await self.ocpp_logic.send_and_wait("ClearChargingProfile", request)

    async def step_a3_change_configuration_test(self):
        """A dedicated test step to change a single configuration value."""
        logger.info("\n\n\n\n\n--- Step A.3: Change Configuration Test ---")
        # This test changes the HeartbeatInterval to 30 seconds as an example.
        request = ChangeConfigurationRequest(key="HeartbeatInterval", value="30")
        await self.ocpp_logic.send_and_wait("ChangeConfiguration", request)

    async def periodic_health_checks(self):
        """
        Continuously requests status and meter values.
        """
        try:
            cycle_count = 0
            while True:
                cycle_count += 1
                logger.info(f"Initiating periodic status and meter value checks for {self.charge_point_id}... (Cycle {cycle_count})")
                await self.ocpp_logic.send_and_wait("TriggerMessage", TriggerMessageRequest(requestedMessage="StatusNotification", connectorId=1))
                await self.ocpp_logic.send_and_wait("TriggerMessage", TriggerMessageRequest(requestedMessage="MeterValues", connectorId=1))
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info(f"Periodic check for {self.charge_point_id} was cancelled.")
        except ConnectionClosedOK:
            logger.info(f"Periodic check for {self.charge_point_id} stopped due to connection closure.")
        except Exception as e:
            logger.error(f"An error occurred during periodic checks for {self.charge_point_id}: {e}")