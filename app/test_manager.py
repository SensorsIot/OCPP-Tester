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
        self.test_sequence = ocpp_handler.test_sequence

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

    async def run_b1_status_and_meter_value_acquisition(self):
        """Runs Step B.1: Status and Meter Value Acquisition."""
        logger.info(f"API triggered: Running Step B.1 for {self.handler.charge_point_id}")
        await self.test_sequence.step_b1_status_and_meter_value_acquisition()

    async def run_d3_smart_charging_capability_test(self):
        """Runs Step D.3: Smart Charging Capability Test."""
        logger.info(f"API triggered: Running Step D.3 for {self.handler.charge_point_id}")
        await self.test_sequence.step_d3_smart_charging_capability_test()

    async def run_d1_set_live_charging_power(self):
        """Runs Step D.1: Set Charging Power (for Active Transaction)."""
        logger.info(f"API triggered: Running Step D.1 for {self.handler.charge_point_id}")
        await self.test_sequence.step_d1_set_live_charging_power()

    async def run_d2_set_default_charging_profile(self):
        """Runs Step D.2: Set Default Charging Profile."""
        logger.info(f"API triggered: Running Step D.2 for {self.handler.charge_point_id}")
        await self.test_sequence.step_d2_set_default_charging_profile()

    async def run_d4_clear_default_charging_profile(self):
        """Runs Step D.4: Clear Default Charging Profile."""
        logger.info(f"API triggered: Running Step D.4 for {self.handler.charge_point_id}")
        await self.test_sequence.step_d4_clear_default_charging_profile()

    async def run_a3_change_configuration_test(self):
        """Runs Step A.3: A dedicated test to change a configuration value."""
        logger.info(f"API triggered: Running Step A.3 for {self.handler.charge_point_id}")
        await self.test_sequence.step_a3_change_configuration_test()