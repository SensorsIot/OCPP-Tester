"""
Global, mutable state for the OCPP server.
"""
from typing import Dict, Any

# A dictionary to store data about connected charge points.
# Format: { "charge_point_id": {"model": "...", "vendor": "...", ...} }
CHARGE_POINTS: Dict[str, Dict[str, Any]] = {}

# A dictionary to store data about ongoing and completed transactions.
# Format: { "transaction_id": {"charge_point_id": "...", "id_tag": "...", ...} }
TRANSACTIONS: Dict[int, Dict[str, Any]] = {}

# A dictionary to store the latest status from the EV simulator.
EV_SIMULATOR_STATE: Dict[str, Any] = {}

# This dictionary will hold server-wide settings that can be changed at runtime.
SERVER_SETTINGS = {
    "use_simulator": False,  # Default to using a real EV (simulator disabled)
    "ev_simulator_available": False  # Tracks if the simulator is reachable
}