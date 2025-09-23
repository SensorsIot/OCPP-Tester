"""
This module contains the TestManager class, which provides a public API
for a web service to trigger specific, on-demand tests for a charge point.
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ocpp_handler import OCPPHandler

logger = logging.getLogger(__name__)

class TestManager:
    """
    Orchestrates the execution of specific, on-demand tests for a charge point.
    This class provides a clean public API for a web service to interact with.
    """
    def __init__(self, ocpp_handler: 'OCPPHandler'):
        self.handler = ocpp_handler
        self.test_sequence = ocpp_handler.ocpp_logic

    async def run_a1_initial_registration(self):
        """Runs Step A.1: Initial Connection and Registration."""
        logger.info(f"API triggered: Running Step A.1 for {self.handler.charge_point_id}")
        await self.test_sequence.step_a1_initial_registration()

    async def run_a2_configuration_exchange(self):
        """Runs Step A.2: Configuration Exchange."""
        logger.info(f"API triggered: Running Step A.2 for {self.handler.charge_point_id}")
        await self.test_sequence.step_a2_configuration_exchange()

    async def run_c1_remote_transaction_test(self):
        """Runs Step C.1: Remote Transaction Test."""
        logger.info(f"API triggered: Running Step C.1 for {self.handler.charge_point_id}")
        await self.test_sequence.step_c1_remote_transaction_test()

    async def run_c2_user_initiated_transaction_test(self):
        """Runs Step C.2: User-Initiated Transaction Test."""
        logger.info(f"API triggered: Running Step C.2 for {self.handler.charge_point_id}")
        await self.test_sequence.step_c2_user_initiated_transaction_test()

    async def run_a6_status_and_meter_value_acquisition(self):
        """Runs Step A.6: Status and Meter Value Acquisition."""
        logger.info(f"API triggered: Running Step A.6 for {self.handler.charge_point_id}")
        await self.test_sequence.step_a6_status_and_meter_value_acquisition()

    async def run_e1_real_world_transaction_test(self):
        """Runs Step E.1: Real-World Transaction Test."""
        logger.info(f"API triggered: Running Step E.1 for {self.handler.charge_point_id}")
        await self.test_sequence.run_e1_real_world_transaction_test()

    async def run_e2_set_charging_profile_6a(self):
        """Runs Step E.2: Set Charging Profile (6A)."""
        logger.info(f"API triggered: Running Step E.2 for {self.handler.charge_point_id}")
        await self.test_sequence.run_e2_set_charging_profile_6a()

    async def run_e3_set_charging_profile_10a(self):
        """Runs Step E.3: Set Charging Profile (10A)."""
        logger.info(f"API triggered: Running Step E.3 for {self.handler.charge_point_id}")
        await self.test_sequence.run_e3_set_charging_profile_10a()

    async def run_e4_set_charging_profile_16a(self):
        """Runs Step E.4: Set Charging Profile (16A)."""
        logger.info(f"API triggered: Running Step E.4 for {self.handler.charge_point_id}")
        await self.test_sequence.run_e4_set_charging_profile_16a()

    async def run_a3_change_configuration_test(self):
        """Runs Step A.3: A dedicated test to change a configuration value."""
        logger.info(f"API triggered: Running Step A.3 for {self.handler.charge_point_id}")
        await self.test_sequence.run_a3_change_configuration_test()

    async def run_a4_check_initial_state(self):
        """Runs Step A.4: Checks the initial status of the charge point."""
        logger.info(f"API triggered: Running Step A.4 for {self.handler.charge_point_id}")
        await self.test_sequence.run_a4_check_initial_state()

    async def run_a5_trigger_all_messages_test(self):
        """Runs Step A.5: Tests all TriggerMessage functionalities."""
        logger.info(f"API triggered: Running Step A.5 for {self.handler.charge_point_id}")
        await self.test_sequence.run_a5_trigger_all_messages_test()