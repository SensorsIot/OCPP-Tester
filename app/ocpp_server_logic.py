"""
Contains the core business logic for the OCPP server.
Delegates message handling and test step execution to dedicated classes.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict

import aiohttp

from app.core import CHARGE_POINTS, TRANSACTIONS, EV_SIMULATOR_STATE, SERVER_SETTINGS, EV_SIMULATOR_BASE_URL
from app.messages import (
    BootNotificationResponse, AuthorizeResponse, DataTransferResponse,
    StatusNotificationResponse, FirmwareStatusNotificationResponse,
    DiagnosticsStatusNotificationResponse, HeartbeatResponse,
    StartTransactionResponse, StopTransactionResponse, MeterValuesResponse,
    BootNotificationRequest, AuthorizeRequest, DataTransferRequest,
    StatusNotificationRequest, FirmwareStatusNotificationRequest,
    DiagnosticsStatusNotificationRequest, HeartbeatRequest,
    StartTransactionRequest, StopTransactionRequest, MeterValuesRequest,
)
from app.ocpp_message_handlers import OcppMessageHandlers, VALID_ID_TAGS, CP_STATE_MAP
from app.ocpp_test_steps import OcppTestSteps

if TYPE_CHECKING:
    from app.ocpp_handler import OCPPHandler

logger = logging.getLogger(__name__)

class OcppServerLogic:
    """
    Contains the core business logic for interacting with a charge point.
    Delegates message handling and test step execution.
    """

    def __init__(self, ocpp_handler: "OCPPHandler", refresh_trigger: asyncio.Event = None, initial_status_received: asyncio.Event = None):
        self.handler = ocpp_handler
        self.charge_point_id = ocpp_handler.charge_point_id
        self.refresh_trigger = refresh_trigger
        self.initial_status_received = initial_status_received
        # Used to wait for specific messages triggered by a test step
        self.pending_triggered_message_events: Dict[str, asyncio.Event] = {}

        self.message_handlers = OcppMessageHandlers(self)
        self.test_steps = OcppTestSteps(self)

    def _check_cancellation(self):
        """Checks if a cancellation has been requested and raises CancelledError if so."""
        if self.handler._cancellation_event.is_set():
            logger.info(f"Cancellation requested for {self.charge_point_id}. Aborting test.")
            raise asyncio.CancelledError("Test cancelled by user.")

    def _set_test_result(self, step_name: str, result: str):
        """Stores the result of a test step in the global state."""
        if self.charge_point_id not in CHARGE_POINTS:
            return
        if "test_results" not in CHARGE_POINTS[self.charge_point_id]:
            CHARGE_POINTS[self.charge_point_id]["test_results"] = {}

        CHARGE_POINTS[self.charge_point_id]["test_results"][step_name] = result
        logger.debug(f"Stored test result for {self.charge_point_id} - {step_name}: {result}")

    async def _set_ev_state(self, state: str):
        """Helper to set EV state and trigger a UI refresh."""
        if not SERVER_SETTINGS.get("ev_simulator_available"):
            logger.info(f"Skipping EV state change to '{state}'; simulator is disabled.")
            # In a real EV scenario, we might log this as an intended action
            # that requires manual intervention.
            return
        set_url = f"{EV_SIMULATOR_BASE_URL}/api/set_state"
        logger.info(f"Setting EV simulator state to '{state}'...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(set_url, json={"state": state}, timeout=5) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to set EV state. Simulator returned {resp.status}")
                        return
                    logger.info(f"Successfully requested EV state change to '{state}'.")
                    # Give the simulator a moment to process the state change
                    await asyncio.sleep(0.2)
                    # Trigger a poll to update the UI
                    if self.refresh_trigger:
                        self.refresh_trigger.set()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Error while setting EV simulator state: {e}")

    async def periodic_health_checks(self):
        """Periodically checks connection health. This is now a passive task."""
        while True:
            self._check_cancellation()
            await asyncio.sleep(60)
            # This check is now passive. The server will rely on the charge
            # point sending heartbeats on its own based on the interval set
            # in the BootNotification response. A more robust implementation
            # could check the `last_heartbeat` timestamp here and close the
            # connection if it's too old. For now, we just wait.
            logger.debug(f"Passive health check for {self.charge_point_id}. Waiting for next heartbeat.")

    async def _wait_for_status(self, status: str):
        while CHARGE_POINTS.get(self.charge_point_id, {}).get("status") != status:
            self._check_cancellation()
            await asyncio.sleep(0.1)

    # --- Delegated Message Handlers ---
    async def handle_boot_notification(self, charge_point_id: str, payload: BootNotificationRequest) -> BootNotificationResponse:
        return await self.message_handlers.handle_boot_notification(charge_point_id, payload)

    async def handle_authorize(self, charge_point_id: str, payload: AuthorizeRequest) -> AuthorizeResponse:
        return await self.message_handlers.handle_authorize(charge_point_id, payload)

    async def handle_data_transfer(self, charge_point_id: str, payload: DataTransferRequest) -> DataTransferResponse:
        return await self.message_handlers.handle_data_transfer(charge_point_id, payload)

    async def handle_status_notification(self, charge_point_id: str, payload: StatusNotificationRequest) -> StatusNotificationResponse:
        return await self.message_handlers.handle_status_notification(charge_point_id, payload)

    async def handle_firmware_status_notification(self, charge_point_id: str, payload: FirmwareStatusNotificationRequest) -> FirmwareStatusNotificationResponse:
        return await self.message_handlers.handle_firmware_status_notification(charge_point_id, payload)

    async def handle_diagnostics_status_notification(self, charge_point_id: str, payload: DiagnosticsStatusNotificationRequest) -> DiagnosticsStatusNotificationResponse:
        return await self.message_handlers.handle_diagnostics_status_notification(charge_point_id, payload)

    async def handle_heartbeat(self, charge_point_id: str, payload: HeartbeatRequest) -> HeartbeatResponse:
        return await self.message_handlers.handle_heartbeat(charge_point_id, payload)

    async def handle_start_transaction(self, charge_point_id: str, payload: StartTransactionRequest) -> StartTransactionResponse:
        return await self.message_handlers.handle_start_transaction(charge_point_id, payload)

    async def handle_stop_transaction(self, charge_point_id: str, payload: StopTransactionRequest) -> StopTransactionResponse:
        return await self.message_handlers.handle_stop_transaction(charge_point_id, payload)

    async def handle_meter_values(self, charge_point_id: str, payload: MeterValuesRequest) -> MeterValuesResponse:
        return await self.message_handlers.handle_meter_values(charge_point_id, payload)

    async def handle_unknown_action(self, charge_point_id: str, payload: dict):
        return await self.message_handlers.handle_unknown_action(charge_point_id, payload)

    # --- Delegated Test Steps ---
    async def run_a1_initial_registration(self):
        return await self.test_steps.run_a1_initial_registration()

    async def run_a2_get_configuration_test(self):
        return await self.test_steps.run_a2_get_configuration_test()

    async def run_a2_configuration_exchange(self):
        return await self.test_steps.run_a2_configuration_exchange()

    async def run_a3_change_configuration_test(self):
        return await self.test_steps.run_a3_change_configuration_test()

    async def run_a4_check_initial_state(self):
        return await self.test_steps.run_a4_check_initial_state()

    async def run_a5_trigger_all_messages_test(self):
        return await self.test_steps.run_a5_trigger_all_messages_test()

    async def run_b1_remote_start_transaction_test(self):
        return await self.test_steps.run_b1_remote_start_transaction_test()

    async def run_b2_remote_stop_transaction_test(self):
        return await self.test_steps.run_b2_remote_stop_transaction_test()

    async def run_b1_status_and_meter_value_acquisition(self):
        return await self.test_steps.run_b1_status_and_meter_value_acquisition()

    async def run_c1_remote_transaction_test(self):
        return await self.test_steps.run_c1_remote_transaction_test()

    async def run_c2_user_initiated_transaction_test(self):
        return await self.test_steps.run_c2_user_initiated_transaction_test()

    async def run_c3_check_power_limits_test(self):
        return await self.test_steps.run_c3_check_power_limits_test()

    async def run_d1_set_live_charging_power(self):
        return await self.test_steps.run_d1_set_live_charging_power()

    async def run_d2_set_default_charging_profile(self):
        return await self.test_steps.run_d2_set_default_charging_profile()

    async def run_d3_smart_charging_capability_test(self):
        return await self.test_steps.run_d3_smart_charging_capability_test()

    async def run_d4_clear_default_charging_profile(self):
        return await self.test_steps.run_d4_clear_default_charging_profile()

    async def run_d5_set_profile_5000w(self):
        return await self.test_steps.run_d5_set_profile_5000w()

    async def run_d6_set_high_charging_profile(self):
        return await self.test_steps.run_d6_set_high_charging_profile()

    async def run_e1_remote_start_state_a(self):
        return await self.test_steps.run_e1_remote_start_state_a()

    async def run_e2_remote_start_state_b(self):
        return await self.test_steps.run_e2_remote_start_state_b()

    async def run_e3_remote_start_state_c(self):
        return await self.test_steps.run_e3_remote_start_state_c()

    async def run_e4_set_profile_6a(self):
        return await self.test_steps.run_e4_set_profile_6a()

    async def run_e5_set_profile_10a(self):
        return await self.test_steps.run_e5_set_profile_10a()

    async def run_e6_set_profile_16a(self):
        return await self.test_steps.run_e6_set_profile_16a()

    async def run_e7_clear_profile(self):
        return await self.test_steps.run_e7_clear_profile()

    async def run_e8_remote_stop_transaction(self):
        return await self.test_steps.run_e8_remote_stop_transaction()

    async def run_e9_brutal_stop(self):
        return await self.test_steps.run_e9_brutal_stop()

    async def run_e10_get_composite_schedule(self):
        return await self.test_steps.run_e10_get_composite_schedule()

    async def run_e11_clear_all_profiles(self):
        return await self.test_steps.run_e11_clear_all_profiles()


