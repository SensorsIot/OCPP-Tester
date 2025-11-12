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
# Import other series as they are created
# from app.tests.test_series_c_charging import TestSeriesC
# from app.tests.test_series_d_smart import TestSeriesD
# from app.tests.test_series_e_remote import TestSeriesE
# from app.tests.test_series_x_utility import TestSeriesX

if TYPE_CHECKING:
    from app.ocpp_server_logic import OcppServerLogic


class OcppTestSteps:
    """
    Facade class that delegates to modular test series classes.

    Maintains backward compatibility with existing code while using
    the new modular structure under app/tests/.

    Test Series Organization:
    - Series A (TestSeriesA): Core Communication & Status (6 tests) - MIGRATED ✓
    - Series B (TestSeriesB): Authorization & Status Management (8 tests) - MIGRATED ✓
    - Series C: Charging Profile Management (7 tests) - TODO
    - Series D: Smart Charging (3 tests) - TODO
    - Series E: Remote Operations (8 tests) - TODO
    - Series X: Utility Functions (2 tests) - TODO
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
        # TODO: Instantiate other series as they are migrated
        # self.series_c = TestSeriesC(ocpp_server_logic)
        # self.series_d = TestSeriesD(ocpp_server_logic)
        # self.series_e = TestSeriesE(ocpp_server_logic)
        # self.series_x = TestSeriesX(ocpp_server_logic)

        # For unmigrated tests, import from monolithic file
        from app.ocpp_test_steps_monolithic import OcppTestSteps as MonolithicTests
        self._monolithic = MonolithicTests(ocpp_server_logic)

    # =========================================================================
    # A-SERIES: Core Communication & Status (MIGRATED ✓)
    # =========================================================================

    async def run_a1_initial_registration(self):
        """A.1: Verifies that the charge point has registered itself."""
        return await self.series_a.run_a1_initial_registration()

    async def run_a2_get_all_parameters(self):
        """A.2: Get All Configuration Parameters"""
        return await self.series_a.run_a2_get_all_parameters()

    async def run_a3_check_single_parameters(self):
        """A.3: Check Single Parameters"""
        return await self.series_a.run_a3_check_single_parameters()

    async def run_a4_check_initial_state(self):
        """A.4: Check Initial State"""
        return await self.series_a.run_a4_check_initial_state()

    async def run_a5_trigger_all_messages_test(self):
        """A.5: Trigger All Messages Test"""
        return await self.series_a.run_a5_trigger_all_messages_test()

    async def run_a6_status_and_meter_value_acquisition(self):
        """A.6: Status and Meter Value Acquisition"""
        return await self.series_a.run_a6_status_and_meter_value_acquisition()

    # =========================================================================
    # B-SERIES: Authorization & Status Management (MIGRATED ✓)
    # =========================================================================

    async def run_b1_reset_transaction_management(self):
        """B.1: Reset Transaction Management"""
        return await self.series_b.run_b1_reset_transaction_management()

    async def run_b1_rfid_public_charging_test(self):
        """B.1: RFID Public Charging Test"""
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

    async def run_b6_clear_rfid_cache(self):
        """B.6: Clear RFID Cache"""
        return await self.series_b.run_b6_clear_rfid_cache()

    async def run_b7_send_rfid_list(self):
        """B.7: Send RFID List"""
        return await self.series_b.run_b7_send_rfid_list()

    async def run_b8_get_rfid_list_version(self):
        """B.8: Get RFID List Version"""
        return await self.series_b.run_b8_get_rfid_list_version()

    # =========================================================================
    # C-SERIES: Charging Profile Management (TODO - delegate to monolithic)
    # =========================================================================

    async def run_c1_set_charging_profile_test(self, params=None):
        """C.1: Set Charging Profile Test"""
        return await self._monolithic.run_c1_set_charging_profile_test(params)

    async def run_c2_user_initiated_transaction_test(self):
        """C.2: User Initiated Transaction Test"""
        return await self._monolithic.run_c2_user_initiated_transaction_test()

    async def run_c2_tx_default_profile_test(self, params=None):
        """C.2: TX Default Profile Test"""
        return await self._monolithic.run_c2_tx_default_profile_test(params)

    async def run_c3_check_power_limits_test(self):
        """C.3: Check Power Limits Test"""
        return await self._monolithic.run_c3_check_power_limits_test()

    async def run_c3_get_composite_schedule_test(self, params=None):
        """C.3: Get Composite Schedule Test"""
        return await self._monolithic.run_c3_get_composite_schedule_test(params)

    async def run_c4_clear_charging_profile_test(self):
        """C.4: Clear Charging Profile Test"""
        return await self._monolithic.run_c4_clear_charging_profile_test()

    async def run_c5_cleanup_test(self):
        """C.5: Cleanup Test"""
        return await self._monolithic.run_c5_cleanup_test()

    # =========================================================================
    # D-SERIES: Smart Charging (TODO - delegate to monolithic)
    # =========================================================================

    async def run_d3_smart_charging_capability_test(self):
        """D.3: Smart Charging Capability Test"""
        return await self._monolithic.run_d3_smart_charging_capability_test()

    async def run_d5_set_profile_5000w(self):
        """D.5: Set Profile 5000W"""
        return await self._monolithic.run_d5_set_profile_5000w()

    async def run_d6_set_high_charging_profile(self):
        """D.6: Set High Charging Profile"""
        return await self._monolithic.run_d6_set_high_charging_profile()

    # =========================================================================
    # E-SERIES: Remote Operations (TODO - delegate to monolithic)
    # =========================================================================

    async def run_e1_remote_start_state_a(self):
        """E.1: Remote Start State A"""
        return await self._monolithic.run_e1_remote_start_state_a()

    async def run_e2_remote_start_state_b(self):
        """E.2: Remote Start State B"""
        return await self._monolithic.run_e2_remote_start_state_b()

    async def run_e3_remote_start_state_c(self):
        """E.3: Remote Start State C"""
        return await self._monolithic.run_e3_remote_start_state_c()

    async def run_e4_set_profile_6a(self):
        """E.4: Set Profile 6A"""
        return await self._monolithic.run_e4_set_profile_6a()

    async def run_e5_set_profile_10a(self):
        """E.5: Set Profile 10A"""
        return await self._monolithic.run_e5_set_profile_10a()

    async def run_e6_set_profile_16a(self):
        """E.6: Set Profile 16A"""
        return await self._monolithic.run_e6_set_profile_16a()

    async def run_e7_clear_profile(self):
        """E.7: Clear Profile"""
        return await self._monolithic.run_e7_clear_profile()

    async def run_e11_clear_all_profiles(self):
        """E.11: Clear All Profiles"""
        return await self._monolithic.run_e11_clear_all_profiles()

    # =========================================================================
    # X-SERIES: Utility Functions (TODO - delegate to monolithic)
    # =========================================================================

    async def run_x1_reboot_wallbox(self):
        """X.1: Reboot Wallbox"""
        return await self._monolithic.run_x1_reboot_wallbox()

    async def run_x2_dump_all_configuration(self):
        """X.2: Dump All Configuration"""
        return await self._monolithic.run_x2_dump_all_configuration()
