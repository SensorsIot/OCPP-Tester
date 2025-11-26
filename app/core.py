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

# OCPP message timeout in seconds
OCPP_MESSAGE_TIMEOUT = int(_env("OCPP_MESSAGE_TIMEOUT", "10"))

CHARGE_POINTS: Dict[str, Dict[str, Any]] = {}
TRANSACTIONS: Dict[int, Dict[str, Any]] = {}
VERIFICATION_RESULTS: Dict[str, Dict[str, Any]] = {}

_active_charge_point_id: Optional[str] = None
_active_transaction_id: Optional[int] = None

_discovered_charge_points: Dict[str, Dict[str, Any]] = {}
_autodiscovery_enabled: bool = True

# Charge points that should have connections rejected (for testing)
_blocked_charge_points: set = set()
_block_all_connections: bool = False

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
    if cp_id in _discovered_charge_points:
        _discovered_charge_points[cp_id]["status"] = "disconnected"

        if _active_charge_point_id == cp_id:
            set_active_charge_point_id(None)
            logger.info(f"🔍 AUTODISCOVERY: Active charge point {cp_id} disconnected, cleared selection")

def is_autodiscovery_enabled() -> bool:
    return _autodiscovery_enabled

def set_autodiscovery_enabled(enabled: bool):
    global _autodiscovery_enabled
    _autodiscovery_enabled = enabled

def block_charge_point(cp_id: str):
    """Block reconnections from a specific charge point (for testing)."""
    _blocked_charge_points.add(cp_id)
    logger.info(f"🚫 Blocking reconnections from charge point: {cp_id}")

def unblock_charge_point(cp_id: str):
    """Allow reconnections from a specific charge point."""
    _blocked_charge_points.discard(cp_id)
    logger.info(f"✅ Allowing reconnections from charge point: {cp_id}")

def is_charge_point_blocked(cp_id: str) -> bool:
    """Check if a charge point is currently blocked."""
    return cp_id in _blocked_charge_points or _block_all_connections

def block_all_connections():
    """Block all OCPP connections (simulates port not listening)."""
    global _block_all_connections
    _block_all_connections = True
    logger.info("🚫 Blocking ALL connections - simulating server offline")

def unblock_all_connections():
    """Allow all OCPP connections again."""
    global _block_all_connections
    _block_all_connections = False
    logger.info("✅ Allowing ALL connections - server back online")

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

# WebSocket server control for testing
_ws_server: Optional[Any] = None
_ws_server_factory: Optional[Any] = None

def set_ws_server(server: Any):
    """Store reference to WebSocket server for test control."""
    global _ws_server
    _ws_server = server

def get_ws_server() -> Optional[Any]:
    """Get reference to WebSocket server."""
    return _ws_server

def set_ws_server_factory(factory: Any):
    """Store factory function to recreate WebSocket server."""
    global _ws_server_factory
    _ws_server_factory = factory

async def stop_ocpp_server():
    """Stop the OCPP WebSocket server (for testing - simulates EVCC offline)."""
    global _ws_server
    if _ws_server is None:
        logger.warning("⚠️ Cannot stop OCPP server - no server reference stored")
        return False

    try:
        logger.info("🛑 Stopping OCPP WebSocket server (closing port 8887)...")
        _ws_server.close()
        await _ws_server.wait_closed()
        logger.info("✅ OCPP WebSocket server stopped - port 8887 closed")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to stop OCPP server: {e}")
        return False

async def start_ocpp_server():
    """Restart the OCPP WebSocket server (for testing - simulates EVCC back online)."""
    global _ws_server, _ws_server_factory
    if _ws_server_factory is None:
        logger.warning("⚠️ Cannot start OCPP server - no factory function stored")
        return False

    try:
        logger.info("🚀 Restarting OCPP WebSocket server (opening port 8887)...")
        _ws_server = await _ws_server_factory()
        logger.info("✅ OCPP WebSocket server restarted - port 8887 listening")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to start OCPP server: {e}")
        return False

EV_SIMULATOR_STATE: Dict[str, Any] = {}

SERVER_SETTINGS = {
    "use_simulator": False,
    "ev_simulator_available": False,
    "ev_simulator_charge_point_id": EV_SIMULATOR_CHARGE_POINT_ID,
    "charging_rate_unit": "A",  # Default to Amperes (most universally supported)
    "charging_rate_unit_auto_detected": False,
    "auto_detection_completed": False,
    "enforce_ocpp_compliance": False,
    "ocpp_host": OCPP_HOST,
    "ocpp_port": OCPP_PORT,
}

CHARGING_RATE_CONFIG = {
    "power_values_w": [4100, 8000, 10000, 11000],
    "current_values_a": [6, 10, 10, 16],
    "test_value_mapping": {
        "disable": {"W": 0, "A": 0},
        "c_default": {"W": 10000, "A": 10},
        "low": {"W": 4100, "A": 6},
        "medium": {"W": 8000, "A": 10},
        "high": {"W": 11000, "A": 16}
    }
}

def get_charging_value(test_level: str) -> tuple[float, str]:
    unit = SERVER_SETTINGS.get("charging_rate_unit", "A")
    value = CHARGING_RATE_CONFIG["test_value_mapping"][test_level][unit]
    return float(value), unit

def get_charging_rate_unit() -> str:
    return SERVER_SETTINGS.get("charging_rate_unit", "A")

def get_current_charging_values(charge_point_id: str) -> tuple[float, float]:
    current_power_w = 0.0
    current_current_a = 0.0

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

    latest_meter_value = meter_values[-1]
    sampled_values = latest_meter_value.sampledValue

    for sv in sampled_values:
        measurand = sv.measurand or ""
        value = sv.value or "0"

        try:
            numeric_value = float(value)

            if measurand == "Power.Active.Import":
                current_power_w = numeric_value
            elif measurand == "Current.Import" and sv.phase == "L1-N":
                current_current_a = numeric_value
        except (ValueError, TypeError):
            continue

    return (current_power_w, current_current_a)

async def auto_detect_charging_rate_unit(ocpp_handler) -> None:
    import logging
    from app.messages import GetConfigurationRequest

    logger = logging.getLogger(__name__)

    try:
        logger.info("🔍 AUTO-DETECT: Requesting all configuration from charge point to detect charging rate unit...")
        logger.debug("🔍 AUTO-DETECT: This is a blocking request with 65s timeout")

        response = await ocpp_handler.send_and_wait(
            "GetConfiguration",
            GetConfigurationRequest(key=[]),
            timeout=65
        )

        if response:
            if process_configuration_response(response):
                return
            logger.info("ℹ️ AUTO-DETECT: 'ChargingScheduleAllowedChargingRateUnit' key not found in configuration, keeping default unit 'A'")
        else:
            logger.warning("⚠️ AUTO-DETECT: GetConfiguration request timed out or returned no response, keeping default unit 'A'")

        SERVER_SETTINGS["auto_detection_completed"] = True

    except Exception as e:
        logger.error(f"❌ AUTO-DETECT: Failed to auto-detect charging rate unit: {e}")
        logger.info("ℹ️ AUTO-DETECT: Keeping default charging rate unit 'A'")
        SERVER_SETTINGS["auto_detection_completed"] = True

def process_configuration_response(response_payload: dict) -> bool:
    import logging
    logger = logging.getLogger(__name__)

    if not response_payload or not response_payload.get("configurationKey"):
        return False

    for key_value in response_payload["configurationKey"]:
        key = key_value.get("key")
        value = key_value.get("value")

        if key == "ChargingScheduleAllowedChargingRateUnit":
            unit_mapping = {
                "Power": "W",
                "Current": "A",
                "W": "W",
                "A": "A"
            }

            # Handle comma-separated values (e.g., "Current, Power")
            values = [v.strip() for v in value.split(",")]

            # Try to map each value
            mapped_units = []
            for v in values:
                if v in unit_mapping:
                    mapped_units.append(unit_mapping[v])

            if mapped_units:
                # Prefer W (Power) over A (Current) when both are available (more precise)
                if "W" in mapped_units:
                    chosen_unit = "W"
                else:
                    chosen_unit = mapped_units[0]

                old_unit = SERVER_SETTINGS.get("charging_rate_unit", "A")
                SERVER_SETTINGS["charging_rate_unit"] = chosen_unit
                SERVER_SETTINGS["charging_rate_unit_auto_detected"] = True
                SERVER_SETTINGS["auto_detection_completed"] = True

                if len(mapped_units) > 1:
                    logger.info(f"✅ AUTO-DETECT: Successfully detected charging rate unit: {chosen_unit} (wallbox supports: {', '.join(mapped_units)}, chose {chosen_unit} over {[u for u in mapped_units if u != chosen_unit]}, previous: {old_unit})")
                else:
                    logger.info(f"✅ AUTO-DETECT: Successfully detected charging rate unit: {chosen_unit} (from value '{value}', previous: {old_unit})")
                return True
            else:
                logger.warning(f"⚠️ AUTO-DETECT: Unsupported charging rate unit value '{value}' in configuration, keeping default 'A'")

    return False