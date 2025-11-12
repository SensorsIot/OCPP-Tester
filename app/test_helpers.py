"""
Test Helper Functions for OCPP Test Steps

This module provides reusable helper functions for common test operations:
- Transaction management (find, stop, wait for start)
- Configuration management (get, set, ensure)
- EV state and connector status management
- Cleanup operations
- User interaction prompts

These functions reduce code duplication across test methods and provide
consistent behavior for common test patterns.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

from app.core import (
    CHARGE_POINTS, TRANSACTIONS, SERVER_SETTINGS,
    OCPP_MESSAGE_TIMEOUT
)
from app.messages import (
    RemoteStopTransactionRequest,
    GetConfigurationRequest,
    ChangeConfigurationRequest,
    ClearChargingProfileRequest
)

logger = logging.getLogger(__name__)


# =============================================================================
# TRANSACTION MANAGEMENT
# =============================================================================

def find_active_transaction(charge_point_id: str) -> Optional[str]:
    """
    Find the active transaction ID for a given charge point.

    Args:
        charge_point_id: The charge point identifier

    Returns:
        Transaction ID if found, None otherwise
    """
    return next(
        (tid for tid, tdata in TRANSACTIONS.items()
         if tdata.get("charge_point_id") == charge_point_id
         and tdata.get("status") == "Ongoing"),
        None
    )


async def stop_active_transaction(
    handler,
    charge_point_id: str,
    timeout: int = OCPP_MESSAGE_TIMEOUT,
    wait_after_stop: float = 3.0
) -> bool:
    """
    Stop any active transaction for a charge point.

    Args:
        handler: OCPP handler instance for sending messages
        charge_point_id: The charge point identifier
        timeout: Timeout for the stop command in seconds
        wait_after_stop: Time to wait after successful stop for StopTransaction message

    Returns:
        True if transaction was stopped successfully or no transaction was active,
        False if stop command failed
    """
    transaction_id = find_active_transaction(charge_point_id)

    if not transaction_id:
        logger.info("   ✅ No active transactions to stop")
        return True

    logger.info(f"   🛑 Stopping active transaction {transaction_id}...")

    try:
        stop_response = await handler.send_and_wait(
            "RemoteStopTransaction",
            RemoteStopTransactionRequest(transactionId=transaction_id),
            timeout=timeout
        )

        if stop_response and stop_response.get("status") == "Accepted":
            logger.info("   ✅ Transaction stopped successfully")
            await asyncio.sleep(wait_after_stop)
            return True
        else:
            status = stop_response.get("status", "Unknown") if stop_response else "No response"
            logger.warning(f"   ⚠️  Stop command status: {status}")
            return False

    except Exception as e:
        logger.warning(f"   ⚠️  Could not stop transaction: {e}")
        return False


async def wait_for_transaction_start(
    charge_point_id: str,
    timeout: float = 15.0,
    check_interval: float = 0.5,
    remote_started: Optional[bool] = None
) -> Optional[str]:
    """
    Wait for a transaction to start for a given charge point.

    Args:
        charge_point_id: The charge point identifier
        timeout: Maximum time to wait in seconds
        check_interval: How often to check for transaction in seconds
        remote_started: If specified, only match transactions with this remote_started flag

    Returns:
        Transaction ID if found, None if timeout
    """
    start_time = asyncio.get_event_loop().time()

    while asyncio.get_event_loop().time() - start_time < timeout:
        await asyncio.sleep(check_interval)

        # Check for new ongoing transaction
        for tx_id, tx_data in TRANSACTIONS.items():
            if tx_data.get("charge_point_id") == charge_point_id:
                if tx_data.get("status") == "Ongoing":
                    # If remote_started filter is specified, check it
                    if remote_started is not None:
                        if tx_data.get("remote_started") == remote_started:
                            return tx_id
                    else:
                        return tx_id

    return None


# =============================================================================
# CONFIGURATION MANAGEMENT
# =============================================================================

async def get_configuration_value(
    handler,
    key: str,
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> Optional[str]:
    """
    Get a single configuration value from the charge point.

    Args:
        handler: OCPP handler instance
        key: Configuration key name
        timeout: Timeout in seconds

    Returns:
        Configuration value as string, or None if not found or error
    """
    try:
        response = await handler.send_and_wait(
            "GetConfiguration",
            GetConfigurationRequest(key=[key]),
            timeout=timeout
        )

        if response and response.get("configurationKey"):
            for config_key in response.get("configurationKey", []):
                if config_key.get("key") == key:
                    return config_key.get("value")

        return None

    except Exception as e:
        logger.warning(f"   ⚠️  Could not get configuration {key}: {e}")
        return None


async def set_configuration_value(
    handler,
    key: str,
    value: str,
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> Tuple[bool, str]:
    """
    Set a configuration value on the charge point.

    Args:
        handler: OCPP handler instance
        key: Configuration key name
        value: Value to set
        timeout: Timeout in seconds

    Returns:
        Tuple of (success: bool, status: str)
        Status can be: "Accepted", "Rejected", "RebootRequired", "NotSupported", "Error"
    """
    try:
        response = await handler.send_and_wait(
            "ChangeConfiguration",
            ChangeConfigurationRequest(key=key, value=value),
            timeout=timeout
        )

        if response and response.get("status"):
            status = response.get("status")
            success = status in ["Accepted", "RebootRequired"]
            return success, status

        return False, "No response"

    except Exception as e:
        logger.warning(f"   ⚠️  Could not set configuration {key}={value}: {e}")
        return False, f"Error: {e}"


async def ensure_configuration(
    handler,
    key: str,
    value: str,
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> Tuple[bool, str]:
    """
    Ensure a configuration value is set, only changing if different.

    This function first checks the current value and only sends ChangeConfiguration
    if the value differs from the desired value.

    Args:
        handler: OCPP handler instance
        key: Configuration key name
        value: Desired value
        timeout: Timeout in seconds

    Returns:
        Tuple of (success: bool, message: str)
    """
    current_value = await get_configuration_value(handler, key, timeout)

    if current_value is not None and current_value.lower() == value.lower():
        logger.info(f"   ✅ {key} already set to '{value}'")
        return True, "Already correct"

    logger.info(f"   🔧 Setting {key}='{value}' (currently: '{current_value}')...")
    success, status = await set_configuration_value(handler, key, value, timeout)

    if success:
        if status == "RebootRequired":
            logger.warning(f"   ⚠️  {key} updated but reboot required")
        else:
            logger.info(f"   ✅ {key} configuration updated")
        return True, status
    else:
        logger.warning(f"   ⚠️  {key} configuration failed: {status}")
        return False, status


async def configure_multiple_parameters(
    handler,
    parameters: List[Dict[str, str]],
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> Tuple[int, int, bool]:
    """
    Configure multiple parameters at once.

    Args:
        handler: OCPP handler instance
        parameters: List of dicts with 'key' and 'value'
        timeout: Timeout for each request

    Returns:
        Tuple of (success_count: int, total_count: int, reboot_required: bool)
    """
    success_count = 0
    total_count = len(parameters)
    reboot_required = False

    for param in parameters:
        key = param.get("key")
        value = param.get("value")

        success, status = await ensure_configuration(handler, key, value, timeout)

        if success:
            success_count += 1
            if status == "RebootRequired":
                reboot_required = True

    return success_count, total_count, reboot_required


# =============================================================================
# STATUS AND STATE MANAGEMENT
# =============================================================================

async def wait_for_connector_status(
    charge_point_id: str,
    status: str,
    timeout: float = 15.0,
    check_interval: float = 0.1
) -> bool:
    """
    Wait for connector to reach a specific status.

    Args:
        charge_point_id: The charge point identifier
        status: Target status (e.g., "Available", "Preparing", "Charging")
        timeout: Maximum time to wait in seconds
        check_interval: How often to check status in seconds

    Returns:
        True if status reached, False if timeout
    """
    start_time = asyncio.get_event_loop().time()

    while asyncio.get_event_loop().time() - start_time < timeout:
        current_status = CHARGE_POINTS.get(charge_point_id, {}).get("status")

        if current_status == status:
            return True

        await asyncio.sleep(check_interval)

    return False


def get_connector_status(charge_point_id: str) -> Optional[str]:
    """
    Get the current connector status for a charge point.

    Args:
        charge_point_id: The charge point identifier

    Returns:
        Current status string or None if not found
    """
    return CHARGE_POINTS.get(charge_point_id, {}).get("status")


def is_using_simulator(charge_point_id: Optional[str] = None) -> bool:
    """
    Check if EV simulator mode is active.

    Args:
        charge_point_id: Optional charge point ID to check specific CP

    Returns:
        True if simulator is active
    """
    if charge_point_id:
        return CHARGE_POINTS.get(charge_point_id, {}).get("use_simulator", False)
    return SERVER_SETTINGS.get("use_simulator", False)


async def set_ev_state_safe(
    ocpp_server_logic,
    state: str
) -> bool:
    """
    Safely set EV simulator state, checking if simulator is enabled.

    Args:
        ocpp_server_logic: Instance of OcppServerLogic with _set_ev_state method
        state: Target state (e.g., "A", "B", "C")

    Returns:
        True if state was set or simulator is disabled, False on error
    """
    if not SERVER_SETTINGS.get("use_simulator"):
        logger.debug(f"Skipping EV state change to '{state}'; simulator is disabled.")
        return True

    try:
        await ocpp_server_logic._set_ev_state(state)
        return True
    except Exception as e:
        logger.error(f"Failed to set EV state to '{state}': {e}")
        return False


# =============================================================================
# EV CONNECTION MANAGEMENT
# =============================================================================

async def prepare_ev_connection(
    handler,
    charge_point_id: str,
    ocpp_server_logic,
    required_status: str = "Preparing",
    timeout: float = 120.0
) -> Tuple[bool, str]:
    """
    Prepare EV connection for testing, handling both simulator and real charge points.

    For simulator mode: Sets state programmatically
    For real CP mode: Checks current status or waits for user to plug in

    Args:
        handler: OCPP handler instance
        charge_point_id: The charge point identifier
        ocpp_server_logic: Instance for setting EV state
        required_status: Required connector status (default: "Preparing")
        timeout: Timeout for waiting for user plug-in

    Returns:
        Tuple of (success: bool, message: str)
    """
    using_simulator = is_using_simulator()
    current_status = get_connector_status(charge_point_id)

    logger.info("🔌 Preparing EV connection...")
    logger.info(f"   💡 Mode: {'EV Simulator' if using_simulator else 'Real Charge Point'}")

    if using_simulator:
        # Using EV simulator - set state programmatically
        logger.info("   🤖 Setting EV simulator to State B (cable connected)...")
        success = await set_ev_state_safe(ocpp_server_logic, "B")

        if not success:
            return False, "Failed to set EV simulator state"

        logger.info("   ✅ EV cable connected (State B)")
        await asyncio.sleep(2)  # Give wallbox time to process
        return True, "Simulator state set"

    else:
        # Real charge point - check status
        logger.info(f"   📊 Current connector status: {current_status}")

        # Check if already in acceptable state
        acceptable_states = [required_status, "SuspendedEV", "SuspendedEVSE"]
        if required_status == "Preparing":
            acceptable_states.append("Preparing")

        if current_status in acceptable_states:
            logger.info("   ✅ EV is already connected and ready")
            return True, f"Already in {current_status} state"

        if current_status == "Charging":
            return False, "Connector is currently charging - cleanup may have failed"

        # Need to wait for user to plug in
        logger.info("")
        logger.info("👤 USER ACTION REQUIRED:")
        logger.info("   🔌 PLEASE PLUG IN YOUR EV CABLE NOW")
        logger.info(f"   ⏳ Waiting for connector status to change to '{required_status}'...")
        logger.info("   💡 The test will continue automatically once EV is detected")
        logger.info("")

        success = await wait_for_connector_status(charge_point_id, required_status, timeout)

        if success:
            logger.info(f"   ✅ EV detected - connector is in {required_status} state")
            return True, f"User plugged in - {required_status} state reached"
        else:
            final_status = get_connector_status(charge_point_id)
            return False, f"Timeout waiting for EV connection. Current status: {final_status}"


# =============================================================================
# CLEANUP OPERATIONS
# =============================================================================

async def cleanup_transaction_and_state(
    handler,
    charge_point_id: str,
    ocpp_server_logic,
    transaction_id: Optional[str] = None,
    target_state: str = "A",
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> bool:
    """
    Complete cleanup: stop transaction, reset EV state, wait for Available status.

    Args:
        handler: OCPP handler instance
        charge_point_id: The charge point identifier
        ocpp_server_logic: Instance for setting EV state
        transaction_id: Optional specific transaction to stop (otherwise finds active)
        target_state: EV state to reset to (default: "A" - unplugged)
        timeout: Timeout for operations

    Returns:
        True if cleanup successful, False otherwise
    """
    logger.info("🧹 Cleaning up: Stopping transaction and resetting EV state...")

    # Find transaction if not specified
    if not transaction_id:
        transaction_id = find_active_transaction(charge_point_id)

    # Stop transaction
    if transaction_id:
        success = await stop_active_transaction(handler, charge_point_id, timeout, wait_after_stop=2.0)
        if not success:
            logger.warning("   ⚠️  Transaction stop failed")
    else:
        logger.info("   ✅ No active transaction to stop")

    # Reset EV state
    if is_using_simulator():
        await set_ev_state_safe(ocpp_server_logic, target_state)
        logger.info(f"   ✅ EV state reset to {target_state} (unplugged)")

    # Wait for Available status
    try:
        success = await wait_for_connector_status(charge_point_id, "Available", timeout)
        if success:
            logger.info("   ✅ Wallbox returned to Available state")
            return True
        else:
            logger.warning("   ⚠️  Timeout waiting for Available status")
            return False
    except asyncio.TimeoutError:
        logger.warning("   ⚠️  Timeout waiting for Available status")
        return False


async def clear_charging_profile(
    handler,
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> bool:
    """
    Clear all charging profiles on the charge point.

    Args:
        handler: OCPP handler instance
        timeout: Timeout in seconds

    Returns:
        True if cleared successfully, False otherwise
    """
    logger.info("   Clearing charging profile...")

    try:
        response = await handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest(),
            timeout=timeout
        )

        if response and response.get("status") == "Accepted":
            logger.info("   ✅ Charging profile cleared")
            return True
        else:
            status = response.get("status", "Unknown") if response else "No response"
            logger.warning(f"   ⚠️  Clear profile failed: {status}")
            return False

    except Exception as e:
        logger.warning(f"   ⚠️  Could not clear profile: {e}")
        return False


# =============================================================================
# LOGGING HELPERS
# =============================================================================

def log_test_start(test_name: str, charge_point_id: str, description: str = None):
    """
    Log standardized test start message.

    Args:
        test_name: Test identifier (e.g., "B.3")
        charge_point_id: The charge point identifier
        description: Optional test description
    """
    logger.info(f"--- Step {test_name}: {description or 'Test'} for {charge_point_id} ---")


def log_test_end(test_name: str, charge_point_id: str):
    """
    Log standardized test end message.

    Args:
        test_name: Test identifier (e.g., "B.3")
        charge_point_id: The charge point identifier
    """
    logger.info(f"--- Step {test_name} for {charge_point_id} complete. ---")


def log_user_action_required(action: str):
    """
    Log a user action required message with standard formatting.

    Args:
        action: Description of the required action
    """
    logger.info("")
    logger.info("👤 USER ACTION REQUIRED:")
    logger.info(f"   {action}")
    logger.info("")
