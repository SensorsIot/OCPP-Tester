"""
Base class for OCPP test series.

Provides shared functionality for all test series including:
- Connection to ocpp_server_logic
- Cancellation checking
- Test result setting
- EV state management
- Status waiting
"""

import logging
from typing import TYPE_CHECKING

from app.core import SERVER_SETTINGS

if TYPE_CHECKING:
    from app.ocpp_server_logic import OcppServerLogic

logger = logging.getLogger(__name__)


class OcppTestBase:
    """
    Base class for all OCPP test series.

    Provides common functionality and abstractions for test execution.
    All test series (A, B, C, D, E, X) inherit from this class.
    """

    def __init__(self, ocpp_server_logic: "OcppServerLogic"):
        """
        Initialize test base with server logic reference.

        Args:
            ocpp_server_logic: OcppServerLogic instance providing OCPP operations
        """
        self.ocpp_server_logic = ocpp_server_logic
        self.handler = ocpp_server_logic.handler
        self.charge_point_id = ocpp_server_logic.charge_point_id
        self.pending_triggered_message_events = ocpp_server_logic.pending_triggered_message_events

    def _check_cancellation(self):
        """
        Check if test execution has been cancelled.

        Raises:
            TestCancelledException: If test was cancelled
        """
        return self.ocpp_server_logic._check_cancellation()

    def _set_test_result(self, step_name: str, result: str):
        """
        Set test result for a specific step.

        Args:
            step_name: Name of the test step
            result: Test result ("PASSED", "FAILED", "SKIPPED", etc.)
        """
        return self.ocpp_server_logic._set_test_result(step_name, result)

    async def _set_ev_state(self, state: str):
        """
        Set EV simulator state (if simulator is enabled).

        Args:
            state: Target EV state (A, B, C, D, E)
        """
        if not SERVER_SETTINGS.get("use_simulator"):
            logger.info(f"Skipping EV state change to '{state}'; simulator is disabled.")
            return
        return await self.ocpp_server_logic._set_ev_state(state)

    async def _wait_for_status(self, status: str):
        """
        Wait for connector to reach a specific status.

        Args:
            status: Target connector status to wait for
        """
        return await self.ocpp_server_logic._wait_for_status(status)
