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

# =============================================================================
# CHARGING PROFILE OPERATIONS
# =============================================================================

async def create_charging_profile(
    connector_id: int,
    charging_profile_id: int,
    stack_level: int,
    purpose: str,
    kind: str,
    charging_unit: str,
    limit: float,
    number_phases: int = 3,
    duration: Optional[int] = None,
    transaction_id: Optional[int] = None,
    start_schedule: Optional[str] = None
):
    """
    Create a ChargingProfile object with specified parameters.

    Args:
        connector_id: Connector ID (0 for charge point level)
        charging_profile_id: Unique profile ID
        stack_level: Profile stack level
        purpose: Profile purpose (TxProfile, TxDefaultProfile, ChargePointMaxProfile)
        kind: Profile kind (Absolute, Recurring, Relative)
        charging_unit: Unit (W for power, A for current)
        limit: Power/current limit value
        number_phases: Number of phases (default: 3)
        duration: Profile duration in seconds (optional)
        transaction_id: Transaction ID for TxProfile (optional)
        start_schedule: ISO8601 timestamp for profile start (optional)

    Returns:
        ChargingProfile object ready to use
    """
    from app.messages import ChargingProfile, ChargingSchedule, ChargingSchedulePeriod
    from datetime import datetime, timezone

    if start_schedule is None:
        start_schedule = datetime.now(timezone.utc).isoformat()

    profile_kwargs = {
        "chargingProfileId": charging_profile_id,
        "stackLevel": stack_level,
        "chargingProfilePurpose": purpose,
        "chargingProfileKind": kind,
        "chargingSchedule": ChargingSchedule(
            chargingRateUnit=charging_unit,
            chargingSchedulePeriod=[
                ChargingSchedulePeriod(
                    startPeriod=0,
                    limit=limit,
                    numberPhases=number_phases
                )
            ],
            startSchedule=start_schedule
        )
    }

    # Add duration only if specified (TxDefaultProfile should not have duration)
    if duration is not None:
        profile_kwargs["chargingSchedule"].duration = duration

    # Add transaction ID only if specified
    if transaction_id is not None:
        profile_kwargs["transactionId"] = transaction_id

    return ChargingProfile(**profile_kwargs)


async def set_charging_profile(
    handler,
    connector_id: int,
    charging_profile,
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> Tuple[bool, str]:
    """
    Send SetChargingProfile request to charge point.

    Args:
        handler: OCPP handler instance
        connector_id: Connector ID
        charging_profile: ChargingProfile object
        timeout: Timeout in seconds

    Returns:
        Tuple of (success: bool, status: str)
    """
    from app.messages import SetChargingProfileRequest

    try:
        response = await handler.send_and_wait(
            "SetChargingProfile",
            SetChargingProfileRequest(
                connectorId=connector_id,
                csChargingProfiles=charging_profile
            ),
            timeout=timeout
        )

        if response and response.get("status"):
            status = response.get("status")
            success = status in ["Accepted", "RebootRequired"]
            return success, status

        return False, "No response"

    except Exception as e:
        logger.warning(f"   ⚠️  Could not set charging profile: {e}")
        return False, f"Error: {e}"


async def get_composite_schedule(
    handler,
    connector_id: int,
    duration: int = 3600,
    charging_rate_unit: Optional[str] = None,
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Get composite charging schedule from charge point.

    Args:
        handler: OCPP handler instance
        connector_id: Connector ID
        duration: Duration in seconds (default: 3600)
        charging_rate_unit: Desired unit (W or A), None for wallbox native
        timeout: Timeout in seconds

    Returns:
        Tuple of (success: bool, schedule_data: Optional[Dict])
        schedule_data contains chargingSchedule if successful
    """
    from app.messages import GetCompositeScheduleRequest

    try:
        response = await handler.send_and_wait(
            "GetCompositeSchedule",
            GetCompositeScheduleRequest(
                connectorId=connector_id,
                duration=duration,
                chargingRateUnit=charging_rate_unit
            ),
            timeout=timeout
        )

        if response and response.get("status") == "Accepted":
            return True, response.get("chargingSchedule")

        status = response.get("status", "Unknown") if response else "No response"
        logger.warning(f"   ⚠️  GetCompositeSchedule failed: {status}")
        return False, None

    except Exception as e:
        logger.warning(f"   ⚠️  Could not get composite schedule: {e}")
        return False, None


async def verify_charging_profile(
    handler,
    connector_id: int,
    expected_unit: str,
    expected_limit: float,
    expected_phases: int = 3,
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Verify charging profile was applied correctly using GetCompositeSchedule.

    Args:
        handler: OCPP handler instance
        connector_id: Connector ID
        expected_unit: Expected charging rate unit (W or A)
        expected_limit: Expected power/current limit
        expected_phases: Expected number of phases
        timeout: Timeout in seconds

    Returns:
        Tuple of (success: bool, verification_results: List[Dict])
    """
    logger.info("🔍 Verifying profile application with GetCompositeSchedule...")
    await asyncio.sleep(2)  # Give wallbox time to process

    success, schedule = await get_composite_schedule(
        handler,
        connector_id,
        duration=3600,
        charging_rate_unit=None,  # Let wallbox return native unit
        timeout=timeout
    )

    verification_results = []

    if not success or not schedule:
        verification_results.append({
            "parameter": "Charging Schedule",
            "expected": "Present",
            "actual": "Not returned",
            "status": "NOT OK"
        })
        return False, verification_results

    # Extract actual values
    actual_unit = schedule.get("chargingRateUnit", "N/A")
    periods = schedule.get("chargingSchedulePeriod", [])
    actual_limit = periods[0].get("limit") if periods else "N/A"
    actual_phases = periods[0].get("numberPhases") if periods else "N/A"

    # Compare expected vs actual
    unit_match = actual_unit == expected_unit
    limit_match = abs(float(actual_limit) - expected_limit) < 0.01 if actual_limit != "N/A" else False
    phases_match = actual_phases == expected_phases if actual_phases != "N/A" else False

    # Build verification results
    verification_results = [
        {
            "parameter": "Number of Phases",
            "expected": str(expected_phases),
            "actual": str(actual_phases),
            "status": "OK" if phases_match else "NOT OK"
        },
        {
            "parameter": "Charging Rate Unit",
            "expected": str(expected_unit),
            "actual": str(actual_unit),
            "status": "OK" if unit_match else "NOT OK"
        },
        {
            "parameter": f"Power Limit ({expected_unit})",
            "expected": str(expected_limit),
            "actual": str(actual_limit),
            "status": "OK" if limit_match else "NOT OK"
        }
    ]

    all_match = unit_match and limit_match
    if all_match:
        logger.info(f"   ✓ Verification passed: {expected_limit}{expected_unit} profile applied correctly")
    else:
        logger.error(f"   ❌ Verification FAILED: Expected {expected_limit}{expected_unit}, got {actual_limit}{actual_unit}")

    return all_match, verification_results


async def clear_all_charging_profiles(
    handler,
    connector_id: Optional[int] = None,
    purpose: Optional[str] = None,
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> bool:
    """
    Clear charging profiles with optional filters.

    Args:
        handler: OCPP handler instance
        connector_id: Optional connector ID filter
        purpose: Optional purpose filter (ChargingProfilePurposeType)
        timeout: Timeout in seconds

    Returns:
        True if cleared successfully
    """
    from app.messages import ClearChargingProfileRequest

    logger.info("   Clearing charging profiles...")

    try:
        request_kwargs = {}
        if connector_id is not None:
            request_kwargs["connectorId"] = connector_id
        if purpose is not None:
            request_kwargs["chargingProfilePurpose"] = purpose

        response = await handler.send_and_wait(
            "ClearChargingProfile",
            ClearChargingProfileRequest(**request_kwargs),
            timeout=timeout
        )

        if response and response.get("status") == "Accepted":
            logger.info("   ✅ Charging profiles cleared")
            return True
        else:
            status = response.get("status", "Unknown") if response else "No response"
            logger.warning(f"   ⚠️  Clear profiles failed: {status}")
            return False

    except Exception as e:
        logger.warning(f"   ⚠️  Could not clear profiles: {e}")
        return False


# =============================================================================
# RFID OPERATIONS
# =============================================================================

async def clear_rfid_cache(
    handler,
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> Tuple[bool, str]:
    """
    Clear RFID authorization cache on charge point.

    Args:
        handler: OCPP handler instance
        timeout: Timeout in seconds

    Returns:
        Tuple of (success: bool, status: str)
    """
    from app.messages import ClearCacheRequest

    logger.info("🗑️  Clearing RFID cache...")

    try:
        response = await handler.send_and_wait(
            "ClearCache",
            ClearCacheRequest(),
            timeout=timeout
        )

        if response is None:
            logger.warning("   ⚠️  ClearCache request timed out")
            return False, "Timeout"

        status = response.get("status", "Unknown")
        logger.info(f"   📝 ClearCache response: {status}")

        if status == "Accepted":
            logger.info("   ✅ RFID cache cleared successfully")
            return True, status
        elif status == "Rejected":
            logger.warning("   ⚠️  ClearCache rejected (wallbox may not support this)")
            return False, status
        else:
            logger.warning(f"   ⚠️  Unexpected status: {status}")
            return False, status

    except Exception as e:
        logger.error(f"   ❌ Error clearing cache: {e}")
        return False, f"Error: {e}"


async def send_local_authorization_list(
    handler,
    rfid_cards: List[Dict[str, str]],
    list_version: int = 1,
    update_type: str = "Full",
    timeout: int = 15
) -> Tuple[bool, str]:
    """
    Send local authorization list (RFID cards) to charge point.

    Args:
        handler: OCPP handler instance
        rfid_cards: List of dicts with 'idTag' and 'status' keys
        list_version: List version number (default: 1)
        update_type: "Full" or "Differential" (default: Full)
        timeout: Timeout in seconds

    Returns:
        Tuple of (success: bool, status: str)

    Example:
        cards = [
            {"idTag": "CARD_001", "status": "Accepted"},
            {"idTag": "CARD_002", "status": "Blocked"}
        ]
        success, status = await send_local_authorization_list(handler, cards)
    """
    from app.messages import SendLocalListRequest, AuthorizationData, IdTagInfo, UpdateType

    logger.info(f"📤 Sending local authorization list ({len(rfid_cards)} cards)...")

    # Convert dict format to OCPP format
    auth_data_list = []
    for card in rfid_cards:
        auth_data_list.append(
            AuthorizationData(
                idTag=card.get("idTag"),
                idTagInfo=IdTagInfo(status=card.get("status", "Accepted"))
            )
        )

    # Log cards being sent
    for i, card in enumerate(rfid_cards, 1):
        status = card.get("status", "Accepted")
        logger.info(f"   🎫 Card {i}: {card.get('idTag')} → {status}")

    try:
        request = SendLocalListRequest(
            listVersion=list_version,
            updateType=UpdateType.Full if update_type == "Full" else UpdateType.Differential,
            localAuthorizationList=auth_data_list
        )

        response = await handler.send_and_wait("SendLocalList", request, timeout=timeout)

        if response is None:
            logger.error("   ❌ SendLocalList request timed out")
            return False, "Timeout"

        status_value = response.get("status", "Unknown")
        logger.info(f"   📝 SendLocalList response: {status_value}")

        if status_value == "Accepted":
            logger.info("   ✅ Local authorization list updated successfully")
            return True, status_value
        elif status_value == "Failed":
            logger.error("   ❌ SendLocalList failed (wallbox could not process the list)")
            return False, status_value
        elif status_value == "VersionMismatch":
            logger.error("   ❌ Version mismatch (list version conflict)")
            return False, status_value
        else:
            logger.warning(f"   ⚠️  Unexpected status: {status_value}")
            return False, status_value

    except Exception as e:
        logger.error(f"   ❌ Error sending local list: {e}")
        return False, f"Error: {e}"


async def get_local_list_version(
    handler,
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> Optional[int]:
    """
    Get the current local authorization list version from charge point.

    Args:
        handler: OCPP handler instance
        timeout: Timeout in seconds

    Returns:
        List version number, or None if error/not supported
    """
    from app.messages import GetLocalListVersionRequest

    logger.info("📋 Getting local authorization list version...")

    try:
        response = await handler.send_and_wait(
            "GetLocalListVersion",
            GetLocalListVersionRequest(),
            timeout=timeout
        )

        if response is None:
            logger.warning("   ⚠️  GetLocalListVersion request timed out")
            return None

        version = response.get("listVersion", -1)
        logger.info(f"   📝 Current list version: {version}")

        if version == 0:
            logger.info("   💡 No local authorization list installed")
        elif version > 0:
            logger.info(f"   ✅ Local list version: {version}")
        else:
            logger.warning("   ⚠️  Invalid list version returned")

        return version if version >= 0 else None

    except Exception as e:
        logger.error(f"   ❌ Error getting list version: {e}")
        return None


# =============================================================================
# REMOTE START/STOP OPERATIONS
# =============================================================================

async def remote_start_transaction(
    handler,
    id_tag: str,
    connector_id: int = 1,
    charging_profile=None,
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> Tuple[bool, str]:
    """
    Send RemoteStartTransaction request to charge point.

    Args:
        handler: OCPP handler instance
        id_tag: ID tag for authorization
        connector_id: Connector ID (default: 1)
        charging_profile: Optional ChargingProfile to apply
        timeout: Timeout in seconds

    Returns:
        Tuple of (success: bool, status: str)
    """
    from app.messages import RemoteStartTransactionRequest

    logger.info(f"📤 Sending RemoteStartTransaction...")
    logger.info(f"   🎫 ID Tag: {id_tag}")
    logger.info(f"   🔌 Connector: {connector_id}")

    try:
        request_kwargs = {
            "idTag": id_tag,
            "connectorId": connector_id
        }
        if charging_profile is not None:
            request_kwargs["chargingProfile"] = charging_profile

        response = await handler.send_and_wait(
            "RemoteStartTransaction",
            RemoteStartTransactionRequest(**request_kwargs),
            timeout=timeout
        )

        if not response:
            logger.error("   ❌ No response received")
            return False, "No response"

        status = response.get("status", "Unknown")

        if status == "Accepted":
            logger.info("   ✅ RemoteStartTransaction accepted by wallbox")
            return True, status
        else:
            logger.error(f"   ❌ RemoteStartTransaction rejected: {status}")
            logger.info("   💡 Possible reasons for rejection:")
            logger.info("      - Connector already in use or faulted")
            logger.info(f"      - Wallbox doesn't recognize idTag '{id_tag}'")
            logger.info("      - Remote start not enabled in wallbox configuration")
            logger.info("      - Wallbox in error state or offline")
            return False, status

    except Exception as e:
        logger.error(f"   ❌ Failed to send RemoteStartTransaction: {e}")
        return False, f"Error: {e}"


async def remote_stop_transaction(
    handler,
    transaction_id: str,
    timeout: int = OCPP_MESSAGE_TIMEOUT
) -> Tuple[bool, str]:
    """
    Send RemoteStopTransaction request to charge point.

    Args:
        handler: OCPP handler instance
        transaction_id: Transaction ID to stop
        timeout: Timeout in seconds

    Returns:
        Tuple of (success: bool, status: str)
    """
    from app.messages import RemoteStopTransactionRequest

    logger.info(f"🛑 Sending RemoteStopTransaction for transaction {transaction_id}...")

    try:
        response = await handler.send_and_wait(
            "RemoteStopTransaction",
            RemoteStopTransactionRequest(transactionId=transaction_id),
            timeout=timeout
        )

        if not response:
            logger.error("   ❌ No response received")
            return False, "No response"

        status = response.get("status", "Unknown")

        if status == "Accepted":
            logger.info("   ✅ RemoteStopTransaction accepted by wallbox")
            return True, status
        else:
            logger.warning(f"   ⚠️  RemoteStopTransaction rejected: {status}")
            return False, status

    except Exception as e:
        logger.error(f"   ❌ Failed to send RemoteStopTransaction: {e}")
        return False, f"Error: {e}"


# =============================================================================
# VERIFICATION AND TEST RESULTS
# =============================================================================

def store_verification_results(
    charge_point_id: str,
    test_name: str,
    results: List[Dict[str, Any]]
):
    """
    Store verification results for display in UI.

    Args:
        charge_point_id: The charge point identifier
        test_name: Test identifier (e.g., "C.1: SetChargingProfile")
        results: List of verification result dicts with keys:
                 parameter, expected, actual, status
    """
    from app.core import VERIFICATION_RESULTS

    key = f"{charge_point_id}_{test_name.split(':')[0].replace('.', '')}"
    VERIFICATION_RESULTS[key] = {
        "test": test_name,
        "results": results
    }
    logger.info(f"📊 Stored verification results for {test_name}: {len(results)} items")


def create_verification_result(
    parameter: str,
    expected: Any,
    actual: Any,
    tolerance: float = 0.0
) -> Dict[str, Any]:
    """
    Create a single verification result entry.

    Args:
        parameter: Parameter name being verified
        expected: Expected value
        actual: Actual value
        tolerance: Tolerance for numeric comparisons (default: 0.0)

    Returns:
        Dict with parameter, expected, actual, and status keys
    """
    # Convert to strings for comparison
    expected_str = str(expected)
    actual_str = str(actual)

    # Try numeric comparison with tolerance if both are numbers
    status = "NOT OK"
    try:
        expected_num = float(expected)
        actual_num = float(actual)
        if abs(expected_num - actual_num) <= tolerance:
            status = "OK"
    except (ValueError, TypeError):
        # Not numbers, do string comparison
        if expected_str == actual_str:
            status = "OK"

    return {
        "parameter": parameter,
        "expected": expected_str,
        "actual": actual_str,
        "status": status
    }


async def start_transaction_for_test(
    handler,
    charge_point_id: str,
    ocpp_server_logic,
    id_tag: str = "TestTransaction",
    connector_id: int = 1,
    timeout: float = 15.0
) -> Optional[str]:
    """
    Start a transaction for testing purposes (used in charging profile tests).

    This helper starts a transaction and waits for it to be confirmed.

    Args:
        handler: OCPP handler instance
        charge_point_id: The charge point identifier
        ocpp_server_logic: Instance for setting EV state
        id_tag: ID tag for the transaction
        connector_id: Connector ID
        timeout: Timeout for transaction start

    Returns:
        Transaction ID if successful, None otherwise
    """
    logger.info("⚠️ No active transaction found. Starting transaction first...")

    # Send RemoteStartTransaction
    success, status = await remote_start_transaction(
        handler,
        id_tag=id_tag,
        connector_id=connector_id
    )

    if not success:
        logger.error(f"FAILURE: RemoteStartTransaction was not accepted. Status: {status}")
        return None

    logger.info("✓ RemoteStartTransaction accepted")

    # Set EV state to C (charging)
    await set_ev_state_safe(ocpp_server_logic, "C")

    # Wait for transaction to start
    transaction_id = await wait_for_transaction_start(
        charge_point_id,
        timeout=timeout,
        check_interval=0.5
    )

    if transaction_id:
        logger.info(f"✓ Transaction {transaction_id} started successfully")
    else:
        logger.error("FAILURE: Transaction did not start within timeout")

    return transaction_id
