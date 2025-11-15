"""
OCPP Test Steps - Modular Facade

This file provides backward compatibility while using the new modular test structure.
All tests are now organized in app/tests/ by series (A, B, C, D, E, X).

The OcppTestSteps class acts as a facade, delegating method calls to the appropriate
test series class. This maintains the existing API while benefiting from the modular
code organization.
"""

from typing import TYPE_CHECKING

from app.tests.test_series_a_basic import TestSeriesA
from app.tests.test_series_b_auth import TestSeriesB
from app.tests.test_series_c_charging import TestSeriesC
from app.tests.test_series_x_utility import TestSeriesX

if TYPE_CHECKING:
    from app.ocpp_server_logic import OcppServerLogic


class OcppTestSteps:
    """
    Facade class that delegates to modular test series classes.

    Maintains backward compatibility with existing code while using
    the new modular structure under app/tests/.

    Test Series Organization (ALL MIGRATED ✓):
    - Series A (TestSeriesA): Core Communication & Status (6 tests)
    - Series B (TestSeriesB): Authorization & Status Management (8 tests)
    - Series C (TestSeriesC): Charging Profile Management (7 tests)
    - Series X (TestSeriesX): Utility Functions (2 tests)
    """

    def __init__(self, ocpp_server_logic: "OcppServerLogic"):
        """
        Initialize facade with all test series.

        Args:
            ocpp_server_logic: OcppServerLogic instance for test execution
        """
        self.ocpp_server_logic = ocpp_server_logic
        self.handler = ocpp_server_logic.handler
        self.charge_point_id = ocpp_server_logic.charge_point_id
        self.pending_triggered_message_events = ocpp_server_logic.pending_triggered_message_events

        # Instantiate all test series
        self.series_a = TestSeriesA(ocpp_server_logic)
        self.series_b = TestSeriesB(ocpp_server_logic)
        self.series_c = TestSeriesC(ocpp_server_logic)
        self.series_x = TestSeriesX(ocpp_server_logic)

    async def run_a1_initial_registration(self):
        """A.1: Verifies that the charge point has registered itself."""
        return await self.series_a.run_a1_initial_registration()

    async def run_a2_get_all_parameters(self):
        """A.2: Get All Configuration Parameters"""
        return await self.series_a.run_a2_get_all_parameters()

    async def run_a3_check_single_parameters(self):
        """A.3: Check Single Parameters"""
        return await self.series_a.run_a3_check_single_parameters()

    async def run_a4_trigger_all_messages_test(self):
        """A.4: Trigger All Messages Test"""
        return await self.series_a.run_a4_trigger_all_messages_test()

    async def run_a5_status_and_meter_value_acquisition(self):
        """A.5: Status and Meter Value Acquisition"""
        return await self.series_a.run_a5_status_and_meter_value_acquisition()

    async def run_a6_evcc_reboot_behavior(self):
        """A.6: EVCC Reboot Behavior"""
        return await self.series_a.run_a6_evcc_reboot_behavior()

    async def run_b1_rfid_public_charging_test(self):
        """B.1: RFID Authorization Before Plug-in (tap-first authorization)"""
        return await self.series_b.run_b1_rfid_public_charging_test()

    async def run_b2_local_cache_authorization_test(self):
        """B.2: Local Cache Authorization Test"""
        return await self.series_b.run_b2_local_cache_authorization_test()

    async def run_b3_remote_smart_charging_test(self, params=None):
        """B.3: Remote Smart Charging Test"""
        return await self.series_b.run_b3_remote_smart_charging_test(params)

    async def run_b4_offline_local_start_test(self, params=None):
        """B.4: Offline Local Start Test"""
        return await self.series_b.run_b4_offline_local_start_test(params)

    async def run_b5_clear_rfid_cache(self):
        """B.5: Clear RFID Cache"""
        return await self.series_b.run_b5_clear_rfid_cache()

    async def run_b6_send_rfid_list(self):
        """B.6: Send RFID List"""
        return await self.series_b.run_b6_send_rfid_list()

    async def run_b7_get_rfid_list_version(self):
        """B.7: Get RFID List Version"""
        return await self.series_b.run_b7_get_rfid_list_version()

    async def run_c1_set_charging_profile_test(self, params=None):
        """C.1: Set Charging Profile Test"""
        return await self.series_c.run_c1_set_charging_profile_test(params)

    async def run_c2_tx_default_profile_test(self, params=None):
        """C.2: TX Default Profile Test"""
        return await self.series_c.run_c2_tx_default_profile_test(params)

    async def run_c3_get_composite_schedule_test(self, params=None):
        """C.3: Get Composite Schedule Test"""
        return await self.series_c.run_c3_get_composite_schedule_test(params)

    async def run_c4_clear_charging_profile_test(self):
        """C.4: Clear Charging Profile Test"""
        return await self.series_c.run_c4_clear_charging_profile_test()

    async def run_c5_cleanup_test(self):
        """C.5: Cleanup Test"""
        return await self.series_c.run_c5_cleanup_test()

    async def run_x1_reboot_wallbox(self):
        """X.1: Reboot Wallbox"""
        return await self.series_x.run_x1_reboot_wallbox()
