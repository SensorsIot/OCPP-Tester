"""
Flask web server providing the REST API + serving the UI.
"""
import asyncio
import inspect
import logging
from typing import Optional

from flask import Flask, jsonify, request, render_template

from app.state import CHARGE_POINTS, EV_SIMULATOR_STATE
from app.ocpp_server_logic import OcppServerLogic
from app.config import EV_SIMULATOR_BASE_URL, OCPP_PORT

import requests

app = Flask(__name__)
app.loop: Optional[asyncio.AbstractEventLoop] = None

def attach_loop(loop: asyncio.AbstractEventLoop):
    """Called from main.py to allow scheduling async test functions."""
    app.loop = loop

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

@app.route("/api/set_ev_state", methods=["POST"])
def set_ev_state():
    data = request.get_json(force=True, silent=True) or {}
    state = data.get("state")
    if not state:
        return jsonify({"error": "State not provided"}), 400

    url = f"{EV_SIMULATOR_BASE_URL}/api/set_state"
    try:
        resp = requests.post(url, json={"state": state}, timeout=5)
        resp.raise_for_status()
        return jsonify({"status": "success", "message": f"EV state set to {state}"})
    except requests.exceptions.RequestException as e:
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
    except asyncio.TimeoutError:
        logging.error(f"API call for '{step_name}' on {charge_point_id} timed out.")
        return jsonify({"error": f"Test step '{step_name}' timed out."}), 504
    except Exception as e:
        logging.exception("Error running test step")
        return jsonify({"error": f"Failed to run step '{step_name}': {e}"}), 500
