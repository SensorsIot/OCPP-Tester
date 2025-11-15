"""
OCPP Test Series X: Utility Functions

This module contains all X-series tests related to:
- Wallbox reboot
- Diagnostic utilities

Test Methods:
- X.1 (run_x1_reboot_wallbox): Reboot wallbox
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from app.core import CHARGE_POINTS, OCPP_MESSAGE_TIMEOUT
from app.messages import (
    ResetRequest, ResetType, GetConfigurationRequest
)
from app.tests.test_base import OcppTestBase

if TYPE_CHECKING:
    from app.ocpp_server_logic import OcppServerLogic

logger = logging.getLogger(__name__)


class TestSeriesX(OcppTestBase):
    """
    Test Series X: Utility Functions (1 test)

    Covers utility operations like reboot.
    """

    async def run_x1_reboot_wallbox(self):
        """X.1: Reboots the wallbox (soft reset)."""
        logger.info(f"--- Step X.1: Rebooting wallbox {self.charge_point_id} ---")
        step_name = "run_x1_reboot_wallbox"
        self._check_cancellation()

        logger.info("Sending Reset (Soft) command to wallbox...")
        success = await self.handler.send_and_wait(
            "Reset",
            ResetRequest(type=ResetType.Soft),
            timeout=OCPP_MESSAGE_TIMEOUT
        )
        self._check_cancellation()

        if success and success.get("status") == "Accepted":
            logger.info("SUCCESS: Reset command was accepted by the wallbox.")
            logger.info("⏳ Wallbox is rebooting... This may take 30-60 seconds.")
            logger.info("💡 The wallbox will reconnect automatically after reboot.")
            logger.info("💡 Watch for new BootNotification in the logs.")
            self._set_test_result(step_name, "PASSED")

            # Optionally wait for disconnect/reconnect
            await asyncio.sleep(2)  # Give wallbox time to process
        else:
            logger.error(f"FAILED: Reset command was not accepted. Response: {success}")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step X.1 for {self.charge_point_id} complete. ---")
