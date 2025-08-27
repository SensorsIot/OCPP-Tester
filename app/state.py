"""
Global, mutable state for the OCPP server.
"""
from typing import Dict, Any, Optional
from app.config import EV_SIMULATOR_CHARGE_POINT_ID

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