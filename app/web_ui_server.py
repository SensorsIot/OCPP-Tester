"""
Flask web server providing the REST API + serving the UI.
"""
import asyncio
import inspect
import logging
import concurrent.futures
from typing import Optional, Dict, Any

import aiohttp
from flask import Flask, jsonify, request, render_template

from app.ocpp_server_logic import OcppServerLogic
from app.ocpp_test_steps import OcppTestSteps
from app.core import CHARGE_POINTS, TRANSACTIONS, EV_SIMULATOR_STATE, SERVER_SETTINGS, get_active_charge_point_id, set_active_charge_point_id, get_active_transaction_id, get_shutdown_event, set_shutdown_event, EV_SIMULATOR_BASE_URL, OCPP_PORT, get_current_charging_values
from app.streamers import EVStatusStreamer

app = Flask(__name__)
app.loop: Optional[asyncio.AbstractEventLoop] = None
app.ev_status_streamer: Optional[EVStatusStreamer] = None

def attach_loop(loop: asyncio.AbstractEventLoop):
    """Called from main.py to allow scheduling async test functions."""
    app.loop = loop

def attach_ev_status_streamer(streamer: EVStatusStreamer):
    """Called from main.py to allow the API to broadcast EV status updates."""
    app.ev_status_streamer = streamer

@app.route("/")
def index():
    # The 'use_simulator' key is now guaranteed to be in SERVER_SETTINGS
    # due to initialization in app/state.py and updates in set_ev_simulator_charge_point_id.
    mode = "EV Simulator" if SERVER_SETTINGS.get("use_simulator", False) else "Live EV"
    return render_template("index.html", ocpp_port=OCPP_PORT, initial_mode=mode)

@app.route("/api/charge_points", methods=["GET"])
def list_charge_points():
    cp_details = {}
    for cp_id, data in CHARGE_POINTS.items():
        # Get current power and current values
        current_power_w, current_current_a = get_current_charging_values(cp_id)

        cp_details[cp_id] = {
            "model": data.get("model"),
            "vendor": data.get("vendor"),
            "status": data.get("status"),
            "boot_time": data.get("boot_time"),
            "first_status_time": data.get("first_status_time"),
            "last_heartbeat": data.get("last_heartbeat"),
            "test_results": data.get("test_results", {}),
            "use_simulator": data.get("use_simulator", False),
            "current_power_w": current_power_w,
            "current_current_a": current_current_a,
            "composite_schedule": data.get("composite_schedule")
        }
    return jsonify({"charge_points": cp_details, "active_charge_point_id": get_active_charge_point_id(), "active_transaction_id": get_active_transaction_id()})

@app.route("/api/transactions", methods=["GET"])
def list_transactions():
    """API endpoint to serve transaction data including MeterValues for the UI."""
    try:
        # Convert transaction keys to strings to avoid JSON serialization issues
        transactions_serializable = {}
        for tx_id, tx_data in TRANSACTIONS.items():
            # Convert all keys to strings for consistent JSON handling
            transactions_serializable[str(tx_id)] = tx_data
        return jsonify({"transactions": transactions_serializable})
    except Exception as e:
        app.logger.error(f"Error serializing transactions: {e}")
        return jsonify({"transactions": {}, "error": str(e)})

@app.route("/api/set_active_charge_point", methods=["POST"])
def set_active_charge_point():
    data = request.get_json(force=True, silent=True) or {}
    charge_point_id = data.get("charge_point_id")

    if not charge_point_id:
        return jsonify({"error": "charge_point_id not provided"}), 400

    if charge_point_id not in CHARGE_POINTS:
        return jsonify({"error": "Charge point not connected."}), 404

    old_active_charge_point_id = get_active_charge_point_id()
    set_active_charge_point_id(charge_point_id)

    logging.info(f"Active charge point changed from {old_active_charge_point_id} to {get_active_charge_point_id()}. Log filtering updated.")

    if old_active_charge_point_id and old_active_charge_point_id != get_active_charge_point_id():
        if old_active_charge_point_id in CHARGE_POINTS:
            prev_ocpp_handler = CHARGE_POINTS[old_active_charge_point_id].get("ocpp_handler")
            if prev_ocpp_handler:
                logging.info(f"Signaling cancellation for previous active CP: {old_active_charge_point_id}")
                prev_ocpp_handler.signal_cancellation()

    return jsonify({"status": f"Active charge point set to {charge_point_id}"})

@app.route("/api/shutdown", methods=["POST"])
def shutdown_server():
    shutdown_event = get_shutdown_event()
    if shutdown_event:
        shutdown_event.set()
        return jsonify({"status": "Server is shutting down..."})
    return jsonify({"error": "Shutdown event not set."}), 500

@app.route("/api/test_steps", methods=["GET"])
def list_test_steps():
    step_methods = [
        name for name, func in inspect.getmembers(OcppTestSteps, inspect.iscoroutinefunction)
        if name.startswith("run_")
    ]
    return jsonify(step_methods)

@app.route("/api/settings", methods=["GET"])
def get_server_settings():
    """Returns server-wide runtime settings, like the EV simulator mode."""
    return jsonify(SERVER_SETTINGS)

@app.route("/api/discovered_charge_points", methods=["GET"])
def get_discovered_charge_points():
    """Returns all discovered charge points with their status."""
    from app.core import get_discovered_charge_points, get_active_charge_point_id, is_autodiscovery_enabled

    discovered = get_discovered_charge_points()
    active_cp_id = get_active_charge_point_id()

    return jsonify({
        "discovered_charge_points": discovered,
        "active_charge_point_id": active_cp_id,
        "autodiscovery_enabled": is_autodiscovery_enabled()
    })

@app.route("/api/autodiscovery", methods=["POST"])
def toggle_autodiscovery():
    """Enable or disable autodiscovery."""
    from app.core import set_autodiscovery_enabled, is_autodiscovery_enabled

    data = request.get_json(force=True, silent=True) or {}
    enabled = data.get("enabled", True)

    set_autodiscovery_enabled(enabled)

    return jsonify({
        "autodiscovery_enabled": is_autodiscovery_enabled(),
        "message": f"Autodiscovery {'enabled' if enabled else 'disabled'}"
    })

@app.route("/api/select_charge_point", methods=["POST"])
def select_charge_point():
    """Manually select a charge point as active."""
    from app.core import set_active_charge_point_id, get_discovered_charge_points

    data = request.get_json(force=True, silent=True) or {}
    charge_point_id = data.get("charge_point_id")

    if not charge_point_id:
        return jsonify({"error": "charge_point_id not provided"}), 400

    discovered = get_discovered_charge_points()
    if charge_point_id not in discovered:
        return jsonify({"error": f"Charge point '{charge_point_id}' not found in discovered list"}), 404

    if discovered[charge_point_id]["status"] != "connected":
        return jsonify({"error": f"Charge point '{charge_point_id}' is not currently connected"}), 400

    set_active_charge_point_id(charge_point_id)

    return jsonify({
        "message": f"Selected charge point '{charge_point_id}' as active",
        "active_charge_point_id": charge_point_id
    })





@app.route("/api/settings/ev_simulator_charge_point_id", methods=["POST"])
def set_ev_simulator_charge_point_id():
    data = request.get_json(force=True, silent=True) or {}
    charge_point_id = data.get("charge_point_id")
    if not charge_point_id:
        return jsonify({"error": "charge_point_id not provided"}), 400

    SERVER_SETTINGS["ev_simulator_charge_point_id"] = charge_point_id

    # Determine if the simulator is active based on the provided charge_point_id
    # and update the global SERVER_SETTINGS accordingly.
    # This ensures the UI correctly reflects whether the simulator is in use.
    if charge_point_id and charge_point_id in CHARGE_POINTS:
        SERVER_SETTINGS["use_simulator"] = True
        # Also update the 'use_simulator' flag for the specific charge point
        # in CHARGE_POINTS, marking it as the simulator.
        for cp_id, cp_data in CHARGE_POINTS.items():
            cp_data["use_simulator"] = (cp_id == charge_point_id)
    else:
        SERVER_SETTINGS["use_simulator"] = False
        # If no simulator is active, ensure all charge points are marked as not being the simulator.
        for cp_id, cp_data in CHARGE_POINTS.items():
            cp_data["use_simulator"] = False


    return jsonify({"status": f"EV simulator charge point ID set to {charge_point_id}"})



@app.route("/api/ev_status", methods=["GET"])
def get_ev_status():
    return jsonify(EV_SIMULATOR_STATE)

@app.route("/api/charging_rate_unit", methods=["GET", "POST"])
def charging_rate_unit():
    if request.method == "GET":
        return jsonify({
            "current_unit": SERVER_SETTINGS.get("charging_rate_unit", "W"),
            "available_units": ["W", "A"],
            "auto_detected": SERVER_SETTINGS.get("charging_rate_unit_auto_detected", False),
            "detection_completed": SERVER_SETTINGS.get("auto_detection_completed", False)
        })

    elif request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        unit = data.get("unit")

        if unit not in ["W", "A"]:
            return jsonify({"error": "Invalid unit. Must be 'W' or 'A'"}), 400

        SERVER_SETTINGS["charging_rate_unit"] = unit
        SERVER_SETTINGS["charging_rate_unit_auto_detected"] = False  # Reset auto-detected flag on manual change
        return jsonify({
            "status": f"Charging rate unit set to {unit}",
            "unit": unit,
            "auto_detected": False
        })


async def _set_and_refresh_ev_state(state: str) -> Dict[str, Any]:
    """Async helper to set the EV state and then immediately poll and broadcast it."""
    # 1. Set the state on the simulator
    set_url = f"{EV_SIMULATOR_BASE_URL}/api/set_state"
    async with aiohttp.ClientSession() as session:
        async with session.post(set_url, json={"state": state}, timeout=5) as resp:
            resp.raise_for_status()
            # Give the simulator a moment to process the state change before we poll it
            await asyncio.sleep(0.2)

    # 2. Poll for the new state
    poll_url = f"{EV_SIMULATOR_BASE_URL}/api/status"
    async with aiohttp.ClientSession() as session:
        async with session.get(poll_url, timeout=5) as resp:
            resp.raise_for_status()
            data = await resp.json()
            EV_SIMULATOR_STATE.update(data)

    # 3. Broadcast the new state to all UI clients
    if app.ev_status_streamer:
        await app.ev_status_streamer.broadcast_status(EV_SIMULATOR_STATE)

    return {
        "status": "success",
        "message": f"EV state set to {state}",
        "newState": EV_SIMULATOR_STATE,
    }

@app.route("/api/set_ev_state", methods=["POST"])
def set_ev_state():
    if not SERVER_SETTINGS.get("use_simulator"):
        return jsonify({"error": "EV simulator is disabled in server settings."}), 403

    data = request.get_json(force=True, silent=True) or {}
    state = data.get("state")
    if not state:
        return jsonify({"error": "State not provided"}), 400

    if not app.loop or not app.loop.is_running():
        return jsonify({"error": "Server loop not available"}), 500

    try:
        coro = _set_and_refresh_ev_state(state)
        future = asyncio.run_coroutine_threadsafe(coro, app.loop)
        result = future.result(timeout=10)
        return jsonify(result)
    except (aiohttp.ClientError, asyncio.TimeoutError, concurrent.futures.TimeoutError) as e:
        logging.error(f"Failed to set EV state via API: {e}")
        return jsonify({"error": f"Failed to set EV state: {e}"}), 500

@app.route("/api/test/<step_name>", methods=["POST"])
def run_test_step(step_name):
    active_charge_point_id = get_active_charge_point_id()

    if not active_charge_point_id:
        return jsonify({"error": "No active charge point selected."}), 400

    charge_point_id = active_charge_point_id

    logging.info(f"API call to run test step '{step_name}' for charge point '{charge_point_id}'")
    if charge_point_id not in CHARGE_POINTS:
        return jsonify({"error": "Charge point not connected."}), 404

    ocpp_handler = CHARGE_POINTS.get(charge_point_id, {}).get("ocpp_handler")
    if not ocpp_handler:
        return jsonify({"error": "Charge point handler not found. The charge point may not have fully booted."}), 404

    if ocpp_handler.test_lock.locked():
        return jsonify({"error": "A test is already running for this charge point."}), 429

    ocpp_logic = ocpp_handler.ocpp_logic
    method = getattr(ocpp_logic.test_steps, step_name, None)
    if not method:
        method = getattr(ocpp_logic, step_name, None)

    if not (method and asyncio.iscoroutinefunction(method) and step_name.startswith("run_")):
        return jsonify({"error": f"Invalid or disallowed test step name: {step_name}"}), 400

    if not app.loop or not app.loop.is_running():
        return jsonify({"error": "Server loop not available"}), 500

    # Get params from request body
    params = request.get_json(silent=True) or {}

    async def run_test_with_lock():
        async with ocpp_handler.test_lock:
            # Pass params to the test method if it accepts them
            sig = inspect.signature(method)
            if 'params' in sig.parameters:
                await method(params=params)
            else:
                await method()

    try:
        future = asyncio.run_coroutine_threadsafe(run_test_with_lock(), app.loop)
        future.result(timeout=120)
        return jsonify({"status": f"Test step '{step_name}' completed for {charge_point_id}."})
    except concurrent.futures.TimeoutError:
        logging.error(f"API call for '{step_name}' on {charge_point_id} timed out.")
        return jsonify({"error": f"Test step '{step_name}' timed out."}), 504
    except Exception as e:
        logging.exception("Error running test step")
        return jsonify({"error": f"Failed to run step '{step_name}': {e}"}), 500
