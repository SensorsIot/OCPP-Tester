"""
Centralized configuration and global, mutable state for the OCPP server app.
Configuration values can be overridden via environment variables.
"""
import os
from typing import Dict, Any, Optional

# --- Helper for environment variables ---
def _env(name: str, default: str) -> str:
    return os.getenv(name, default)

# --- OCPP / WebSockets Configuration ---
OCPP_HOST = _env("OCPP_HOST", "0.0.0.0")
OCPP_PORT = int(_env("OCPP_PORT", "8887"))

# Paths on the same OCPP_PORT (one server with a path router).
LOG_WS_PATH = _env("LOG_WS_PATH", "/logs")
EV_STATUS_WS_PATH = _env("EV_STATUS_WS_PATH", "/ev-status")

# --- HTTP (Flask via uvicorn) Configuration ---
HTTP_HOST = _env("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(_env("HTTP_PORT", "5000"))

# Where to find the UI index.html (absolute or relative)
UI_INDEX_PATH = _env("UI_INDEX_PATH", "app/templates/index.html")

# --- EV Simulator Configuration ---
EV_SIMULATOR_BASE_URL = _env("EV_SIMULATOR_BASE_URL", "http://192.168.0.151")
EV_SIMULATOR_CHARGE_POINT_ID = _env("EV_SIMULATOR_CHARGE_POINT_ID", "Wallbox001")
EV_STATUS_POLL_INTERVAL = int(_env("EV_STATUS_POLL_INTERVAL", "5"))  # seconds
EV_WAIT_MAX_BACKOFF = int(_env("EV_WAIT_MAX_BACKOFF", "30"))         # seconds

# --- Global, mutable state for the OCPP server ---

# A dictionary to store data about connected charge points.
# Format: { "charge_point_id": {"model": "...", "vendor": "...", ...} }
CHARGE_POINTS: Dict[str, Dict[str, Any]] = {}

# A dictionary to store data about ongoing and completed transactions.
# Format: { "transaction_id": {"charge_point_id": "...", "id_tag": "...", ...} }
TRANSACTIONS: Dict[int, Dict[str, Any]] = {}

# A string to store the ID of the currently active charge point selected in the UI.
_active_charge_point_id: Optional[str] = None

def get_active_charge_point_id() -> Optional[str]:
    return _active_charge_point_id

def set_active_charge_point_id(cp_id: Optional[str]):
    global _active_charge_point_id
    _active_charge_point_id = cp_id

# A dictionary to store the latest status from the EV simulator.
EV_SIMULATOR_STATE: Dict[str, Any] = {}

# This dictionary will hold server-wide settings that can be changed at runtime.
SERVER_SETTINGS = {
    "use_simulator": False,  # Controlled by UI/config: True if EV simulator mode is active
    "ev_simulator_available": False,  # Tracks if the simulator service is reachable
    "ev_simulator_charge_point_id": EV_SIMULATOR_CHARGE_POINT_ID,
}