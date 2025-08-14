"""
This module contains the Flask web server logic. It provides API endpoints
for a web UI to interact with the OCPP server's state and trigger test commands.
"""
from flask import Flask, jsonify, request, render_template
import os
import asyncio
import requests
import inspect
import logging
from app.state import CHARGE_POINTS
from app.test_manager import TestManager
from app.ev_simulator_state import EV_SIMULATOR_STATE

# To ensure Flask finds the templates, we provide an explicit, absolute path to the template folder.
template_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates')
app = Flask(__name__, template_folder=template_dir)
 
@app.route('/api/charge_points', methods=['GET'])
def list_charge_points():
    """
    API endpoint to get a dictionary of all currently connected charge points
    with their details.
    """
    # Create a serializable copy, excluding the non-serializable handler object
    cp_details = {
        cp_id: {
            "model": data.get("model"),
            "vendor": data.get("vendor"),
            "status": data.get("status"),
            "last_heartbeat": data.get("last_heartbeat")
        }
        for cp_id, data in CHARGE_POINTS.items()
    }
    return jsonify(cp_details)

@app.route('/api/test_steps', methods=['GET'])
def list_test_steps():
    """
    API endpoint to get a list of available test step methods from the TestManager class.
    """
    step_methods = [
        name for name, func in inspect.getmembers(TestManager, inspect.isfunction)
        if name.startswith('run_')
    ]
    return jsonify(step_methods)

@app.route('/api/ev_status', methods=['GET'])
def get_ev_status():
    """API endpoint to get the current status of the EV simulator."""
    return jsonify(EV_SIMULATOR_STATE)

@app.route('/api/set_ev_state', methods=['POST'])
def set_ev_state():
    """API endpoint to set the state of the EV simulator."""
    data = request.get_json()
    state = data.get('state')
    if not state:
        return jsonify({"error": "State not provided"}), 400

    # The IP address of the EV simulator.
    url = "http://192.168.0.81/api/set_state"
    try:
        response = requests.post(url, json={"state": state}, timeout=5)
        response.raise_for_status() # Raise an exception for bad status codes
        return jsonify({"status": "success", "message": f"EV state set to {state}"})
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to set EV state: {e}"}), 500

@app.route('/api/test/<path:charge_point_id>/<step_name>', methods=['POST'])
def run_test_step(charge_point_id, step_name):
    """
    API endpoint to trigger a specific test step for a connected charge point.
    This now awaits the test completion to provide feedback to the UI.
    """
    if charge_point_id not in CHARGE_POINTS:
        return jsonify({"error": "Charge point not connected."}), 404
        
    charge_point_state = CHARGE_POINTS.get(charge_point_id, {})
    ocpp_handler = charge_point_state.get('ocpp_handler')
    if not ocpp_handler:
        return jsonify({"error": "Charge point handler not found. The charge point may not have fully booted."}), 404

    # Use the TestManager for a safer, more explicit API
    test_manager = ocpp_handler.test_manager
    method = getattr(test_manager, step_name, None)
    # Check that the method exists and starts with 'run_' for security
    if not (method and asyncio.iscoroutinefunction(method) and step_name.startswith('run_')):
        return jsonify({"error": f"Invalid or disallowed test step name: {step_name}"}), 400

    try:
        # Since this Flask view runs in a separate thread from the main asyncio
        # event loop, we use `run_coroutine_threadsafe` to schedule the async
        # test method and then block on its result.
        loop = app.loop
        future = asyncio.run_coroutine_threadsafe(method(), loop)
        # Add a slightly longer timeout to catch application-level timeouts.
        future.result(timeout=35)
        return jsonify({"status": f"Test step '{step_name}' completed for {charge_point_id}."})
    except asyncio.TimeoutError:
        # This can be from future.result() or the underlying OCPP call.
        logging.error(f"API call for '{step_name}' on {charge_point_id} timed out.")
        return jsonify({"error": f"Test step '{step_name}' timed out. No response from charge point."}), 504 # Gateway Timeout
    except Exception as e:
        # This will catch other exceptions from the coroutine.
        logging.error(f"An error occurred during test step '{step_name}' for {charge_point_id}: {e}", exc_info=True)
        return jsonify({"error": f"An internal error occurred during test step '{step_name}'."}), 500

@app.route('/', methods=['GET'])
def home():
    """
    Serves the main web UI page.
    """
    return render_template('index.html')