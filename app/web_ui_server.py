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

from app.state import CHARGE_POINTS, EV_SIMULATOR_STATE
from app.ocpp_server_logic import OcppServerLogic
from app.config import EV_SIMULATOR_BASE_URL, OCPP_PORT
from app.status_streamer import EVStatusStreamer

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
    return render_template("index.html", ocpp_port=OCPP_PORT)

@app.route("/api/charge_points", methods=["GET"])
def list_charge_points():
    cp_details = {
        cp_id: {
            "model": data.get("model"),
            "vendor": data.get("vendor"),
            "status": data.get("status"),
            "last_heartbeat": data.get("last_heartbeat"),
        }
        for cp_id, data in CHARGE_POINTS.items()
    }
    return jsonify(cp_details)

@app.route("/api/test_steps", methods=["GET"])
def list_test_steps():
    step_methods = [
        name for name, func in inspect.getmembers(OcppServerLogic, inspect.iscoroutinefunction)
        if name.startswith("run_")
    ]
    return jsonify(step_methods)

@app.route("/api/ev_status", methods=["GET"])
def get_ev_status():
    return jsonify(EV_SIMULATOR_STATE)

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

@app.route("/api/test/<path:charge_point_id>/<step_name>", methods=["POST"])
def run_test_step(charge_point_id, step_name):
    if charge_point_id not in CHARGE_POINTS:
        return jsonify({"error": "Charge point not connected."}), 404

    ocpp_handler = CHARGE_POINTS.get(charge_point_id, {}).get("ocpp_handler")
    if not ocpp_handler:
        return jsonify({"error": "Charge point handler not found. The charge point may not have fully booted."}), 404

    ocpp_logic = ocpp_handler.ocpp_logic
    method = getattr(ocpp_logic, step_name, None)

    if not (method and asyncio.iscoroutinefunction(method) and step_name.startswith("run_")):
        return jsonify({"error": f"Invalid or disallowed test step name: {step_name}"}), 400

    if not app.loop or not app.loop.is_running():
        return jsonify({"error": "Server loop not available"}), 500

    try:
        future = asyncio.run_coroutine_threadsafe(method(), app.loop)
        future.result(timeout=120)
        return jsonify({"status": f"Test step '{step_name}' completed for {charge_point_id}."})
    except concurrent.futures.TimeoutError:
        logging.error(f"API call for '{step_name}' on {charge_point_id} timed out.")
        return jsonify({"error": f"Test step '{step_name}' timed out."}), 504
    except Exception as e:
        logging.exception("Error running test step")
        return jsonify({"error": f"Failed to run step '{step_name}': {e}"}), 500
