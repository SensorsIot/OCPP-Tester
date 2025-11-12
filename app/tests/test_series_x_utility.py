"""
OCPP Test Series X: Utility Functions

This module contains all X-series tests related to:
- Wallbox reboot
- Configuration dumps
- Diagnostic utilities

Test Methods:
- X.1 (run_x1_reboot_wallbox): Reboot wallbox
- X.2 (run_x2_dump_all_configuration): Dump all configuration parameters
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
    Test Series X: Utility Functions (2 tests)

    Covers utility operations like reboot and configuration dumps.
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

    async def run_x2_dump_all_configuration(self):
        """X.2: Dumps ALL configuration parameters to log."""
        logger.info(f"--- Step X.2: Dumping all configuration for {self.charge_point_id} ---")
        step_name = "run_x2_dump_all_configuration"
        self._check_cancellation()

        logger.info("📋 Requesting ALL configuration parameters...")
        response = await self.handler.send_and_wait(
            "GetConfiguration",
            GetConfigurationRequest(),  # No key = get all
            timeout=OCPP_MESSAGE_TIMEOUT
        )
        self._check_cancellation()

        if response and response.get("configurationKey"):
            config_keys = response.get("configurationKey", [])
            unknown_keys = response.get("unknownKey", [])

            logger.info("=" * 80)
            logger.info(f"📊 CONFIGURATION DUMP FOR {self.charge_point_id}")
            logger.info("=" * 80)
            logger.info(f"Total parameters: {len(config_keys)}")
            if unknown_keys:
                logger.info(f"Unknown parameters: {len(unknown_keys)}")
            logger.info("-" * 80)

            # Group parameters by category for easier reading
            categories = {
                "Connection": [],
                "Authorization": [],
                "Transaction": [],
                "Charging": [],
                "Meter": [],
                "Local": [],
                "Security": [],
                "Other": []
            }

            for key_data in config_keys:
                key = key_data.get("key", "Unknown")
                value = key_data.get("value", "N/A")
                readonly = key_data.get("readonly", False)

                # Categorize parameter
                if any(x in key for x in ["Heartbeat", "Connection", "Timeout", "WebSocket"]):
                    categories["Connection"].append((key, value, readonly))
                elif any(x in key for x in ["Authorize", "Auth", "LocalList", "Cache", "RFID"]):
                    categories["Authorization"].append((key, value, readonly))
                elif any(x in key for x in ["Transaction", "Stop", "Start", "IdTag"]):
                    categories["Transaction"].append((key, value, readonly))
                elif any(x in key for x in ["Charging", "Profile", "Schedule", "Power"]):
                    categories["Charging"].append((key, value, readonly))
                elif any(x in key for x in ["Meter", "Value", "Sample", "Clock"]):
                    categories["Meter"].append((key, value, readonly))
                elif any(x in key for x in ["Local", "Offline"]):
                    categories["Local"].append((key, value, readonly))
                elif any(x in key for x in ["Security", "Certificate", "Cert"]):
                    categories["Security"].append((key, value, readonly))
                else:
                    categories["Other"].append((key, value, readonly))

            # Print each category
            for category, params in categories.items():
                if params:
                    logger.info(f"\n📁 {category} Parameters ({len(params)}):")
                    for key, value, readonly in sorted(params):
                        ro_marker = " [RO]" if readonly else ""
                        logger.info(f"   {key}: {value}{ro_marker}")

            if unknown_keys:
                logger.info("\n⚠️  Unknown Parameters:")
                for unknown in unknown_keys:
                    logger.info(f"   {unknown}")

            logger.info("=" * 80)
            logger.info("✅ Configuration dump complete")
            logger.info("=" * 80)

            self._set_test_result(step_name, "PASSED")
        else:
            logger.error(f"FAILED: GetConfiguration did not return config keys. Response: {response}")
            self._set_test_result(step_name, "FAILED")

        logger.info(f"--- Step X.2 for {self.charge_point_id} complete. ---")
