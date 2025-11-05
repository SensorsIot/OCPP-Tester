"""
Centralized configuration and global, mutable state for the OCPP server app.
Configuration values can be overridden via environment variables.
"""
import os
import logging
from typing import Dict, Any, Optional
import asyncio

logger = logging.getLogger(__name__)

def _env(name: str, default: str) -> str:
    return os.getenv(name, default)

OCPP_HOST = _env("OCPP_HOST", "0.0.0.0")
OCPP_PORT = int(_env("OCPP_PORT", "8887"))

LOG_WS_PATH = _env("LOG_WS_PATH", "/logs")
EV_STATUS_WS_PATH = _env("EV_STATUS_WS_PATH", "/ev-status")

HTTP_HOST = _env("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(_env("HTTP_PORT", "5000"))

UI_INDEX_PATH = _env("UI_INDEX_PATH", "app/templates/index.html")

EV_SIMULATOR_BASE_URL = _env("EV_SIMULATOR_BASE_URL", "http://192.168.0.151")
EV_SIMULATOR_CHARGE_POINT_ID = _env("EV_SIMULATOR_CHARGE_POINT_ID", "Wallbox001")
EV_STATUS_POLL_INTERVAL = int(_env("EV_STATUS_POLL_INTERVAL", "5"))
EV_WAIT_MAX_BACKOFF = int(_env("EV_WAIT_MAX_BACKOFF", "30"))


CHARGE_POINTS: Dict[str, Dict[str, Any]] = {}

TRANSACTIONS: Dict[int, Dict[str, Any]] = {}

_active_charge_point_id: Optional[str] = None
_active_transaction_id: Optional[int] = None

_discovered_charge_points: Dict[str, Dict[str, Any]] = {}
_autodiscovery_enabled: bool = True

def get_active_charge_point_id() -> Optional[str]:
    return _active_charge_point_id

def set_active_charge_point_id(cp_id: Optional[str]):
    global _active_charge_point_id
    _active_charge_point_id = cp_id

def get_discovered_charge_points() -> Dict[str, Dict[str, Any]]:
    """Return all discovered charge points with their connection status."""
    return _discovered_charge_points.copy()

def register_discovered_charge_point(cp_id: str, connection_info: Dict[str, Any]):
    """Register a newly discovered charge point."""
    global _active_charge_point_id

    _discovered_charge_points[cp_id] = {
        "status": "connected",
        "first_seen": connection_info.get("timestamp"),
        "remote_address": connection_info.get("remote_address"),
        "connection_count": _discovered_charge_points.get(cp_id, {}).get("connection_count", 0) + 1
    }

    if _autodiscovery_enabled and _active_charge_point_id is None:
        _active_charge_point_id = cp_id
        logger.info(f"🔍 AUTODISCOVERY: Automatically selected first charge point: {cp_id}")
        return True

    return False

def unregister_charge_point(cp_id: str):
    """Mark a charge point as disconnected."""
    if cp_id in _discovered_charge_points:
        _discovered_charge_points[cp_id]["status"] = "disconnected"

        # If this was the active charge point, clear it
        if _active_charge_point_id == cp_id:
            set_active_charge_point_id(None)
            logger.info(f"🔍 AUTODISCOVERY: Active charge point {cp_id} disconnected, cleared selection")

def is_autodiscovery_enabled() -> bool:
    return _autodiscovery_enabled

def set_autodiscovery_enabled(enabled: bool):
    global _autodiscovery_enabled
    _autodiscovery_enabled = enabled

def get_active_transaction_id() -> Optional[int]:
    return _active_transaction_id

def set_active_transaction_id(tx_id: Optional[int]):
    global _active_transaction_id
    _active_transaction_id = tx_id

_shutdown_event: Optional[asyncio.Event] = None

def get_shutdown_event() -> Optional[asyncio.Event]:
    return _shutdown_event

def set_shutdown_event(event: asyncio.Event):
    global _shutdown_event
    _shutdown_event = event

# A dictionary to store the latest status from the EV simulator.
EV_SIMULATOR_STATE: Dict[str, Any] = {}

# This dictionary will hold server-wide settings that can be changed at runtime.
SERVER_SETTINGS = {
    "use_simulator": False,  # Controlled by UI/config: True if EV simulator mode is active
    "ev_simulator_available": False,  # Tracks if the simulator service is reachable
    "ev_simulator_charge_point_id": EV_SIMULATOR_CHARGE_POINT_ID,
    "charging_rate_unit": "W",  # "W" for Watts or "A" for Amperes - default setting
    "charging_rate_unit_auto_detected": False,  # True if unit was auto-detected from charge point
    "auto_detection_completed": False,  # True when auto-detection attempt has finished (success or failure) - start as False to enable auto-detection
    "enforce_ocpp_compliance": False,  # Set to True to reject protocol violations (strict mode)
    "ocpp_host": OCPP_HOST,  # OCPP WebSocket host
    "ocpp_port": OCPP_PORT,  # OCPP WebSocket port
}

# Predefined charging power/current values for tests
# Based on actual Actec wallbox capabilities: 130A max @ 230V = ~30kW max
CHARGING_RATE_CONFIG = {
    "power_values_w": [6900, 13800, 23000, 29900],  # Watts (30A, 60A, 100A, 130A @ 230V)
    "current_values_a": [30, 60, 100, 130],         # Amperes (actual wallbox current levels)
    "test_value_mapping": {
        "disable": {"W": 0, "A": 0},           # 0W or 0A (disable charging)
        "low": {"W": 6900, "A": 30},           # Low power: 6900W or 30A (230V × 30A)
        "medium": {"W": 13800, "A": 60},       # Medium power: 13800W or 60A (230V × 60A)
        "high": {"W": 23000, "A": 100},        # High power: 23000W or 100A (230V × 100A)
        "max": {"W": 29900, "A": 130}          # Max power: 29900W or 130A (wallbox maximum)
    }
}

def get_charging_value(test_level: str) -> tuple[float, str]:
    """
    Get the appropriate charging value and unit based on current configuration.

    Args:
        test_level: "disable", "low", "medium", or "high"

    Returns:
        tuple of (value, unit) e.g., (6000, "W") or (8, "A")
    """
    unit = SERVER_SETTINGS.get("charging_rate_unit", "A") # Default to A
    value = CHARGING_RATE_CONFIG["test_value_mapping"][test_level][unit]
    return float(value), unit

def get_charging_rate_unit() -> str:
    """Get the current charging rate unit (W or A)."""
    return SERVER_SETTINGS.get("charging_rate_unit", "A") # Default to A

def get_current_charging_values(charge_point_id: str) -> tuple[float, float]:
    """
    Extract current power and current from the latest meter values for a charge point.

    Args:
        charge_point_id: The ID of the charge point

    Returns:
        tuple of (current_power_w, current_current_a) - returns (0.0, 0.0) if no data
    """
    current_power_w = 0.0
    current_current_a = 0.0

    # Find the active transaction for this charge point
    active_transaction = None
    for transaction_id, transaction_data in TRANSACTIONS.items():
        if (transaction_data.get("charge_point_id") == charge_point_id and
            transaction_data.get("status") == "Ongoing"):
            active_transaction = transaction_data
            break

    if not active_transaction:
        return (current_power_w, current_current_a)

    meter_values = active_transaction.get("meter_values", [])
    if not meter_values:
        return (current_power_w, current_current_a)

    # Get the latest meter value entry
    latest_meter_value = meter_values[-1]
    sampled_values = latest_meter_value.sampledValue

    # Extract power and current values
    for sv in sampled_values:
        measurand = sv.measurand or ""
        value = sv.value or "0"

        try:
            numeric_value = float(value)

            if measurand == "Power.Active.Import":
                current_power_w = numeric_value
            elif measurand == "Current.Import" and sv.phase == "L1-N":
                # Use L1-N phase current as representative current
                current_current_a = numeric_value
        except (ValueError, TypeError):
            continue

    return (current_power_w, current_current_a)

async def auto_detect_charging_rate_unit(ocpp_handler) -> None:
    """
    Auto-detect the charging rate unit supported by the charge point.
    Reads ChargingScheduleAllowedChargingRateUnit from GetConfiguration response.
    """
    import logging
    from app.messages import GetConfigurationRequest

    logger = logging.getLogger(__name__)

    try:
        logger.info("🔍 Auto-detecting charging rate unit from charge point configuration...")

        # Request all configuration keys since this charge point has GetConfigurationMaxKeys=1
        # and may not handle specific key requests properly
        # Use a longer timeout since configuration requests can be slow
        # Add extra buffer time to avoid race conditions with timing precision
        response = await ocpp_handler.send_and_wait(
            "GetConfiguration",
            GetConfigurationRequest(key=[]),
            timeout=65
        )

        if response:
            # Try to process the configuration response
            if process_configuration_response(response):
                return  # Successfully detected

        logger.info("ℹ️ ChargingScheduleAllowedChargingRateUnit not found, keeping default unit 'A'")
        SERVER_SETTINGS["auto_detection_completed"] = True

    except Exception as e:
        logger.error(f"❌ Failed to auto-detect charging rate unit: {e}")
        logger.info("ℹ️ Keeping default charging rate unit 'A'")
        SERVER_SETTINGS["auto_detection_completed"] = True

def process_configuration_response(response_payload: dict) -> bool:
    """
    Process a GetConfiguration response and extract charging rate unit.
    Returns True if detection was successful, False otherwise.
    """
    import logging
    logger = logging.getLogger(__name__)

    if not response_payload or not response_payload.get("configurationKey"):
        return False

    for key_value in response_payload["configurationKey"]:
        key = key_value.get("key")
        value = key_value.get("value")

        if key == "ChargingScheduleAllowedChargingRateUnit":
            # Map charge point responses to our internal units
            unit_mapping = {
                "Power": "W",  # Power means Watts
                "Current": "A",  # Current means Amperes
                "W": "W",      # Direct mapping
                "A": "A"       # Direct mapping
            }

            mapped_unit = unit_mapping.get(value)
            if mapped_unit:
                old_unit = SERVER_SETTINGS.get("charging_rate_unit", "A")
                SERVER_SETTINGS["charging_rate_unit"] = mapped_unit
                SERVER_SETTINGS["charging_rate_unit_auto_detected"] = True
                SERVER_SETTINGS["auto_detection_completed"] = True
                logger.info(f"✅ Auto-detected charging rate unit: {mapped_unit} (from '{value}', was: {old_unit})")
                return True
            else:
                logger.warning(f"⚠️ Unsupported charging rate unit: {value}, keeping default")

    return False