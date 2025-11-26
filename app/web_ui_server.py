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
from app.core import CHARGE_POINTS, TRANSACTIONS, EV_SIMULATOR_STATE, SERVER_SETTINGS, VERIFICATION_RESULTS, get_active_charge_point_id, set_active_charge_point_id, get_active_transaction_id, get_shutdown_event, set_shutdown_event, EV_SIMULATOR_BASE_URL, OCPP_PORT, get_current_charging_values, OCPP_MESSAGE_TIMEOUT
from app.streamers import EVStatusStreamer

async def ensure_status_known(ocpp_handler, charge_point_id: str) -> None:
    """Get current status by triggering StatusNotification."""
    from app.core import CHARGE_POINTS, OCPP_MESSAGE_TIMEOUT
    from app.messages import TriggerMessageRequest
    import asyncio

    logging.info(f"Getting current status for {charge_point_id}...")
    try:
        trigger_response = await ocpp_handler.send_and_wait(
            "TriggerMessage",
            TriggerMessageRequest(requestedMessage="StatusNotification", connectorId=1),
            timeout=OCPP_MESSAGE_TIMEOUT
        )
        if trigger_response and trigger_response.get("status") == "Accepted":
            logging.info("StatusNotification trigger accepted, waiting for response...")
            await asyncio.sleep(2)  # Wait for StatusNotification to arrive
            cp_status = CHARGE_POINTS.get(charge_point_id, {}).get("status")
            logging.info(f"Current status: {cp_status}")
        else:
            logging.warning(f"StatusNotification trigger failed: {trigger_response}")
    except Exception as e:
        logging.warning(f"Failed to trigger StatusNotification: {e}")

def get_connection_status(charge_point_id: str) -> dict:
    """Detect and return the current connection status for the charge point."""
    from app.core import SERVER_SETTINGS, CHARGE_POINTS

    # Check if EV simulator is available and in use
    ev_sim_available = SERVER_SETTINGS.get("ev_simulator_available", False)
    ev_sim_in_use = CHARGE_POINTS.get(charge_point_id, {}).get("use_simulator", False)

    # Check if a real EV is connected (look at charge point status)
    cp_status = CHARGE_POINTS.get(charge_point_id, {}).get("status")

    # Determine connection type
    if ev_sim_available and ev_sim_in_use:
        connection_type = "EV Simulator Connected"
        details = "Using simulated EV for testing"
    elif cp_status in ["Preparing", "Charging", "SuspendedEV", "SuspendedEVSE", "Finishing"]:
        connection_type = "Real EV Connected"
        details = f"Real EV detected (Status: {cp_status})"
    elif cp_status == "Available":
        connection_type = "No EV Connected"
        details = "Charge point available, waiting for EV"
    elif cp_status == "Unavailable":
        connection_type = "Charge Point Unavailable"
        details = "Charge point is unavailable"
    elif cp_status == "Faulted":
        connection_type = "Charge Point Faulted"
        details = "Charge point has a fault condition"
    else:
        connection_type = "Unknown"
        details = f"Status: {cp_status or 'Not reported'}"

    return {
        "type": connection_type,
        "details": details,
        "status": cp_status or "Unknown"
    }

OCPP_COMMAND_DESCRIPTIONS = {
    "BootNotification": "Charge point sends its identification and registration information to the server",
    "Heartbeat": "Periodic signal from charge point to indicate it's online and operational",
    "StatusNotification": "Charge point reports its current operational status and connector state",
    "Authorize": "Request to verify if an ID tag (RFID card) is authorized to start charging",
    "StartTransaction": "Notification that a charging transaction has started",
    "StopTransaction": "Notification that a charging transaction has stopped",
    "MeterValues": "Periodic energy consumption and power measurements from the charge point",
    "DataTransfer": "Custom vendor-specific data exchange between charge point and server",

    "GetConfiguration": "Request all or specific configuration parameters from the charge point",
    "ChangeConfiguration": "Modify a specific configuration parameter on the charge point",
    "GetCompositeSchedule": "Retrieve the calculated charging schedule currently active on the charge point",
    "SetChargingProfile": "Send a charging profile (power/current limits over time) to the charge point",
    "ClearChargingProfile": "Remove one or more charging profiles from the charge point",
    "RemoteStartTransaction": "Command the charge point to start a charging session remotely",
    "RemoteStopTransaction": "Command the charge point to stop an ongoing charging session",
    "TriggerMessage": "Request the charge point to send a specific OCPP message immediately",
    "Reset": "Command the charge point to reboot (soft or hard reset)",
    "UnlockConnector": "Command the charge point to unlock a specific connector",
    "GetDiagnostics": "Request the charge point to upload diagnostic log files",
    "UpdateFirmware": "Command the charge point to download and install new firmware",
    "ReserveNow": "Reserve a charge point for a specific ID tag",
    "CancelReservation": "Cancel an existing reservation",
    "ClearCache": "Clear the authorization cache (RFID list) on the charge point",
    "SendLocalList": "Send or update the local authorization list (RFID cards) on the charge point",
    "GetLocalListVersion": "Get the version number of the local authorization list",
}

def get_ocpp_description(action: str) -> str:
    """Get the description for an OCPP command."""
    return OCPP_COMMAND_DESCRIPTIONS.get(action, "OCPP command")

app = Flask(__name__)
app.loop: Optional[asyncio.AbstractEventLoop] = None
app.ev_status_streamer: Optional[EVStatusStreamer] = None

def attach_loop(loop: asyncio.AbstractEventLoop):
    """Called from ocpp-tester.py to allow scheduling async test functions."""
    app.loop = loop

def attach_ev_status_streamer(streamer: EVStatusStreamer):
    """Called from ocpp-tester.py to allow the API to broadcast EV status updates."""
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
            "configuration_details": data.get("configuration_details", {}),
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

@app.route("/api/version", methods=["GET"])
def get_version():
    """Returns version information for the OCPP Tester."""
    try:
        from app.version import get_version_info, get_version_string
        import datetime

        version_info = get_version_info()
        version_info["startup_time"] = SERVER_SETTINGS.get("startup_time", datetime.datetime.now().isoformat())
        version_info["version_string"] = get_version_string()

        return jsonify(version_info)
    except Exception as e:
        logging.exception("Error getting version info")
        return jsonify({"error": f"Failed to get version: {e}"}), 500

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

@app.route("/api/charging_profile_defaults", methods=["GET"])
def get_charging_profile_defaults():
    """Get default charging profile values based on current configuration."""
    from app.core import get_charging_value

    unit = SERVER_SETTINGS.get("charging_rate_unit", "A")

    # C.1 and C.2 both use "medium" as default (10A or 8000W)
    medium_value, _ = get_charging_value("medium")

    return jsonify({
        "current_unit": unit,
        "c1": {"unit": unit, "limit": medium_value},
        "c2": {"unit": unit, "limit": medium_value}
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
    import os
    from datetime import datetime
    from dataclasses import asdict, is_dataclass

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

    # Prepare log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = "/home/ocpp-tester/logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{step_name}_{charge_point_id}_{timestamp}.log")

    # Message log storage
    message_log = []

    # Execution log storage (for test logger.info calls)
    execution_log = []

    # Create a logging handler to capture test execution logs
    class TestLogHandler(logging.Handler):
        def emit(self, record):
            # Only capture logs from test modules
            if 'app.tests' in record.name or 'app.test_helpers' in record.name:
                timestamp_str = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                execution_log.append({
                    "timestamp": timestamp_str,
                    "level": record.levelname,
                    "message": record.getMessage()
                })

    test_log_handler = TestLogHandler()
    test_log_handler.setLevel(logging.INFO)

    # Add handler to capture logs
    root_logger = logging.getLogger()
    root_logger.addHandler(test_log_handler)

    # Track triggered messages
    triggered_messages = set()

    def log_message(msg_type: str, action: str, payload: Any, timestamp_str: str, message_id: str = None, test_name: str = None):
        """Helper to log OCPP messages with full OCPP message format.

        Smart filtering:
        - A.6 test: Log ALL messages (complete OCPP trace needed)
        - Other tests: Filter out Heartbeat, StatusNotification, MeterValues unless explicitly triggered
        - Always log REQUEST/RESPONSE (test-initiated actions)
        """
        if is_dataclass(payload):
            payload_dict = asdict(payload)
        elif isinstance(payload, dict):
            payload_dict = payload
        else:
            payload_dict = {"raw": str(payload)}

        # Build full OCPP message array
        if msg_type == "REQUEST":
            # CALL format: [2, message_id, action, payload]
            full_ocpp_message = [2, message_id, action, payload_dict]

            # Track if we're triggering StatusNotification or BootNotification
            if action == "TriggerMessage":
                requested_message = payload_dict.get("requestedMessage")
                if requested_message in ["StatusNotification", "BootNotification"]:
                    triggered_messages.add(requested_message)

        elif msg_type == "RESPONSE":
            # CALLRESULT format: [3, message_id, payload]
            full_ocpp_message = [3, message_id, payload_dict]
        elif msg_type == "RECEIVED":
            # CALL format from charge point: [2, message_id, action, payload]
            full_ocpp_message = [2, message_id, action, payload_dict]
        else:
            full_ocpp_message = None

        # Smart filtering for RECEIVED messages (from charge point)
        if msg_type == "RECEIVED":
            # A.6 test: log ALL messages (needs complete trace of reconnection behavior)
            if test_name and "a6" in test_name.lower():
                pass  # Don't filter - log everything
            # Other tests: filter noise unless explicitly triggered
            elif action in ["Heartbeat", "StatusNotification", "MeterValues"]:
                # Don't log unless this message was explicitly triggered by the test
                if action not in triggered_messages:
                    return  # Skip logging this message
                # If it was triggered, log it and remove from triggered set
                triggered_messages.discard(action)

        message_log.append({
            "timestamp": timestamp_str,
            "type": msg_type,
            "action": action,
            "payload": payload_dict,
            "message_id": message_id,
            "full_ocpp_message": full_ocpp_message
        })

    # Wrap send_and_wait to capture messages
    original_send_and_wait = ocpp_handler.send_and_wait
    import uuid

    async def wrapped_send_and_wait(action: str, payload: Any, timeout: int = OCPP_MESSAGE_TIMEOUT):
        """Wrapper to log all OCPP requests and responses."""
        # Generate message ID (same as what send_and_wait will generate)
        message_id = str(uuid.uuid4())

        request_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_message("REQUEST", action, payload, request_timestamp, message_id, test_name=step_name)

        response = await original_send_and_wait(action, payload, timeout)

        response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # Check if timeout occurred (response is None)
        if response is None:
            log_message("RESPONSE_TIMEOUT", action, {"error": f"Timeout after {timeout}s - no response received from charge point"}, response_timestamp, message_id, test_name=step_name)
        else:
            log_message("RESPONSE", action, response, response_timestamp, message_id, test_name=step_name)

        return response

    async def run_test_with_lock():
        async with ocpp_handler.test_lock:
            # Set up wrappers BEFORE getting status so all messages are logged
            ocpp_handler.send_and_wait = wrapped_send_and_wait
            ocpp_handler.incoming_message_logger = log_message

            # Store wrappers as attributes so they can be transferred if handler changes (e.g., during A.6 test)
            ocpp_handler._test_wrapped_send_and_wait = wrapped_send_and_wait
            ocpp_handler._test_log_message = log_message
            ocpp_handler._original_send_and_wait = original_send_and_wait

            # Get current status only for tests that need it (skip A and B series)
            if not (step_name.startswith("run_a") or step_name.startswith("run_b")):
                await ensure_status_known(ocpp_handler, charge_point_id)

            # Log the detected status as a manual entry for summary
            status_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            cp_status = CHARGE_POINTS.get(charge_point_id, {}).get("status", "Unknown")
            message_log.append({
                "timestamp": status_timestamp,
                "type": "STATUS_DETECTED",
                "action": "StatusNotification",
                "payload": {"connectorId": 1, "status": cp_status},
                "message_id": None,
                "full_ocpp_message": None
            })

            try:
                # Pass params to the test method if it accepts them
                sig = inspect.signature(method)
                if 'params' in sig.parameters:
                    await method(params=params)
                else:
                    await method()
            finally:
                # Restore original send_and_wait and clear logger
                ocpp_handler.send_and_wait = original_send_and_wait
                ocpp_handler.incoming_message_logger = None
                # Remove test log handler
                root_logger.removeHandler(test_log_handler)

    try:
        future = asyncio.run_coroutine_threadsafe(run_test_with_lock(), app.loop)
        future.result(timeout=300)  # 5 minutes timeout for long tests

        # Write comprehensive log file
        with open(log_file, "w") as f:
            f.write("=" * 80 + "\n")
            f.write(f"OCPP 1.6J - {step_name} - Comprehensive Log\n")
            f.write("=" * 80 + "\n")
            f.write(f"Charge Point ID: {charge_point_id}\n")
            f.write(f"Test Start Time: {timestamp}\n")
            f.write(f"Server: OCPP Test Server\n")

            # Add connection status detection using the status we captured at test start
            # Find the STATUS_DETECTED entry in message_log
            detected_status = None
            for msg in message_log:
                if msg['type'] == 'STATUS_DETECTED':
                    detected_status = msg['payload']['status']
                    break

            # If we found detected status, use it; otherwise query current status
            if detected_status:
                from app.core import SERVER_SETTINGS
                ev_sim_available = SERVER_SETTINGS.get("ev_simulator_available", False)

                # If EV simulator is available, assume it's being used for testing
                if ev_sim_available:
                    connection_type = "EV Simulator"
                    details = f"Using EV simulator (Status: {detected_status})"
                elif detected_status in ["Preparing", "Charging", "SuspendedEV", "SuspendedEVSE", "Finishing"]:
                    connection_type = "Real EV Connected"
                    details = f"Real EV detected (Status: {detected_status})"
                elif detected_status == "Available":
                    connection_type = "No EV Connected"
                    details = "Charge point available, waiting for EV"
                elif detected_status == "Unavailable":
                    connection_type = "Charge Point Unavailable"
                    details = "Charge point is unavailable"
                elif detected_status == "Faulted":
                    connection_type = "Charge Point Faulted"
                    details = "Charge point has a fault condition"
                else:
                    connection_type = "Unknown"
                    details = f"Status: {detected_status or 'Not reported'}"

                f.write(f"Connection Type: {connection_type}\n")
                f.write(f"Details: {details}\n")
            else:
                # Fallback to querying current status if no STATUS_DETECTED entry found
                conn_status = get_connection_status(charge_point_id)
                f.write(f"Connection Type: {conn_status['type']}\n")
                f.write(f"Details: {conn_status['details']}\n")

            f.write("=" * 80 + "\n\n")

            import json

            # For A.3 test, write raw GetConfiguration response
            if step_name == "run_a3_check_single_parameters":
                # Find GetConfiguration response in message log
                for msg in message_log:
                    if msg['action'] == 'GetConfiguration' and msg['type'] == 'RESPONSE':
                        f.write("RAW GETCONFIGURATION RESPONSE\n")
                        f.write("=" * 80 + "\n")
                        f.write(json.dumps(msg['payload'], indent=2))
                        f.write("\n" + "=" * 80 + "\n\n")
                        break

            # Get test results
            test_results = CHARGE_POINTS[charge_point_id].get("test_results", {})
            result_data = test_results.get(step_name, "NOT RUN")

            # Handle both old string format and new dict format
            if isinstance(result_data, dict):
                result = result_data.get("result", "NOT RUN")
                reason = result_data.get("reason")
            else:
                result = result_data
                reason = None

            f.write(f"TEST RESULT: {result}\n")
            if reason:
                f.write(f"Reason: {reason}\n")
            f.write("-" * 80 + "\n\n")

            # Don't write generic "TEST EXECUTION LOG" header - phases have their own headers

            # Tag execution logs for merging
            all_logs = []
            for exec_log in execution_log:
                all_logs.append({
                    "timestamp": exec_log["timestamp"],
                    "log_type": "EXECUTION",
                    "data": exec_log
                })

            for ocpp_msg in message_log:
                all_logs.append({
                    "timestamp": ocpp_msg["timestamp"],
                    "log_type": "OCPP",
                    "data": ocpp_msg
                })

            # Sort by timestamp
            all_logs.sort(key=lambda x: x["timestamp"])

            # If no logs and test was skipped, add explanation
            if not all_logs and result == "SKIPPED":
                f.write("INFO: TEST SKIPPED - No activity logged\n")
                f.write("=" * 80 + "\n\n")

            # Build a map of message_id -> REQUEST for matching RESPONSE
            request_map = {}
            for msg in message_log:
                if msg.get('type') == 'REQUEST':
                    msg_id = msg.get('message_id')
                    if msg_id:
                        request_map[msg_id] = msg

            # Helper function to get descriptive REQUEST title and key parameter
            def get_request_info(action, payload):
                """Generate descriptive title and key parameter for REQUEST"""
                if action == 'GetConfiguration':
                    keys = payload.get('key', [])
                    if keys and len(keys) == 1:
                        return keys[0], f"Check {keys[0]} setting"
                    return "Configuration", f"Check {len(keys)} parameters" if keys else "Retrieve all parameters"
                elif action == 'ChangeConfiguration':
                    key = payload.get('key', '')
                    value = payload.get('value', '')
                    return key, f"Set {key} to {value}"
                elif action == 'RemoteStartTransaction':
                    id_tag = payload.get('idTag', '')
                    return id_tag, f"Start charging with {id_tag}"
                elif action == 'RemoteStopTransaction':
                    tx_id = payload.get('transactionId', '')
                    return f"Transaction {tx_id}", f"Stop transaction {tx_id}"
                elif action == 'SetChargingProfile':
                    return "Charging Limit", "Apply charging profile"
                elif action == 'ClearCache':
                    return "Authorization Cache", "Clear local authorization cache"
                elif action == 'SendLocalList':
                    return "RFID List", "Send RFID authorization list"
                elif action == 'GetLocalListVersion':
                    return "RFID List Version", "Get RFID list version"
                elif action == 'Reset':
                    reset_type = payload.get('type', 'Hard')
                    return reset_type, f"Reboot wallbox ({reset_type})"
                else:
                    return action, action

            # Helper function to extract inline context from RESPONSE
            def get_response_context(action, payload):
                """Extract key information from RESPONSE payload for inline display"""
                if action == 'GetConfiguration':
                    keys = payload.get('configurationKey', [])
                    if keys and len(keys) == 1:
                        value = keys[0].get('value', 'N/A')
                        return f"Current value is '{value}'"
                    return f"Retrieved {len(keys)} parameters" if keys else "No parameters"
                elif action == 'ChangeConfiguration':
                    status = payload.get('status', '')
                    return f"Status: {status}"
                elif action in ['RemoteStartTransaction', 'RemoteStopTransaction']:
                    status = payload.get('status', '')
                    return f"Status: {status}"
                elif action == 'ClearCache':
                    status = payload.get('status', '')
                    return f"Status: {status}"
                elif action == 'SendLocalList':
                    status = payload.get('status', '')
                    return f"Status: {status}"
                elif action == 'GetLocalListVersion':
                    version = payload.get('listVersion', 0)
                    return f"Version: {version}"
                elif action == 'Authorize':
                    status = payload.get('idTagInfo', {}).get('status', 'Unknown')
                    return f"Authorization: {status}"
                elif action == 'StartTransaction':
                    tx_id = payload.get('idTagInfo', {}).get('transactionId', payload.get('transactionId', 'N/A'))
                    return f"Transaction ID: {tx_id}"
                else:
                    status = payload.get('status', '')
                    return f"Status: {status}" if status else ""

            # Helper function to generate narrative message based on response
            def get_narrative_message(action, payload, is_response=True):
                """Generate INFO/WARNING/ERROR narrative message"""
                if not is_response:
                    return None

                if action == 'GetConfiguration':
                    keys = payload.get('configurationKey', [])
                    if keys and len(keys) == 1:
                        key_name = keys[0].get('key', '')
                        value = keys[0].get('value', '')
                        return f"INFO: [OK] {key_name} is set to '{value}'."
                    return None
                elif action == 'ChangeConfiguration':
                    status = payload.get('status', '')
                    if status == 'Accepted':
                        return "INFO: [OK] Configuration updated successfully."
                    elif status == 'Rejected':
                        return "ERROR: Configuration change rejected by charge point."
                    elif status == 'RebootRequired':
                        return "WARNING: Configuration updated but requires reboot to take effect."
                    return None
                elif action == 'RemoteStartTransaction':
                    status = payload.get('status', '')
                    if status == 'Accepted':
                        return "INFO: [OK] Remote start command accepted."
                    elif status == 'Rejected':
                        return "ERROR: Remote start rejected - connector may be unavailable or in use."
                    return None
                elif action == 'RemoteStopTransaction':
                    status = payload.get('status', '')
                    if status == 'Accepted':
                        return "INFO: [OK] Remote stop command accepted."
                    elif status == 'Rejected':
                        return "ERROR: Remote stop rejected - transaction may not exist."
                    return None
                elif action == 'ClearCache':
                    status = payload.get('status', '')
                    if status == 'Accepted':
                        return "INFO: [OK] Authorization cache cleared successfully."
                    elif status == 'Rejected':
                        return "WARNING: Cache clear rejected - may have protected entries."
                    return None
                elif action == 'Authorize':
                    auth_status = payload.get('idTagInfo', {}).get('status', '')
                    if auth_status == 'Accepted':
                        return "INFO: [OK] RFID tag authorized."
                    elif auth_status == 'Invalid':
                        return "ERROR: RFID tag not recognized or invalid."
                    elif auth_status == 'Blocked':
                        return "ERROR: RFID tag is blocked."
                    return None
                return None

            # Helper function to check if message should be filtered
            def should_filter_message(msg):
                """Returns True if message should be filtered out (not logged)"""
                # Show ALL messages for ALL tests (no filtering)
                return False

            # Helper to clean emoji from message
            def clean_emojis(message):
                """Replace common emojis with ASCII equivalents"""
                message = message.replace('✅', '[OK]')
                message = message.replace('❌', '[ERROR]')
                message = message.replace('⚠️', '[WARNING]')
                message = message.replace('ℹ️', '[INFO]')
                message = message.replace('📋', '')
                message = message.replace('🔧', '')
                message = message.replace('⏳', '[WAITING]')
                message = message.replace('🎫', '')
                message = message.replace('📘', '')
                message = message.replace('⚡', '')
                message = message.replace('🏷️', '')
                message = message.replace('🔌', '')
                message = message.replace('🧹', '[CLEANUP]')
                message = message.replace('💡', '[TIP]')
                message = message.replace('🔍', '')
                message = message.replace('📤', '')
                message = message.replace('📡', '')
                message = message.replace('🔄', '')
                message = message.replace('📱', '')
                message = message.replace('🛑', '')
                return message

            # Helper to determine if an INFO message should be filtered
            def should_filter_info_message(message):
                """Filter out verbose descriptive messages, keep only essential ones"""
                # Filter out these step-by-step execution patterns only
                filter_patterns = [
                    "Pre-test check",
                    "Resetting EV state",
                    "Waiting for wallbox",
                    "Wallbox is now in",
                    "ready for test",
                    "Step 1:",
                    "Step 2:",
                    "Step 3:",
                    "Step 4:",
                    "Step 5:",
                    "Plugging in EV",
                    "cable connected",
                    "Waiting for automatic",
                    "automatically started",
                    "Default idTag",
                    "Common values",
                    "Verifying charging session"
                ]

                for pattern in filter_patterns:
                    if pattern in message:
                        return True
                return False

            def is_scenario_description(message):
                """Check if message is part of scenario description"""
                description_patterns = [
                    "This tests",
                    "Use case",
                    "[TIP]",
                    "TEST",  # Like "PLUG-AND-CHARGE TEST"
                ]
                return any(pattern in message for pattern in description_patterns)

            # Process messages chronologically - show execution logs AND JSON messages
            sequence_num = 0

            for log_entry in all_logs:
                # Skip execution logs (INFO/WARNING/ERROR messages) - only show JSON
                if log_entry["log_type"] == "EXECUTION":
                    continue

                # Handle OCPP messages only
                msg = log_entry["data"]

                # Skip status detected and filtered messages (Heartbeat, StatusNotification, MeterValues)
                if msg['type'] == 'STATUS_DETECTED' or should_filter_message(msg):
                    continue

                # Handle REQUEST messages
                if msg['type'] == 'REQUEST':
                    sequence_num += 1
                    f.write(f"### Sequence {sequence_num}: {msg['action']} ###\n\n")
                    f.write(f"[{msg['timestamp']}] REQUEST (Server -> CP): {msg['action']}\n")
                    if msg.get('full_ocpp_message'):
                        f.write(json.dumps(msg['full_ocpp_message'], indent=2))
                    else:
                        f.write(json.dumps(msg['payload'], indent=2))
                    f.write("\n\n")

                # Handle RESPONSE messages
                elif msg['type'] in ['RESPONSE', 'RESPONSE_TIMEOUT']:
                    if msg['type'] == 'RESPONSE_TIMEOUT':
                        f.write(f"[{msg['timestamp']}] RESPONSE (CP -> Server): TIMEOUT\n")
                        f.write(f"ERROR: {msg['payload'].get('error', 'Timeout occurred')}\n\n")
                    else:
                        f.write(f"[{msg['timestamp']}] RESPONSE (CP -> Server)\n")
                        if msg.get('full_ocpp_message'):
                            f.write(json.dumps(msg['full_ocpp_message'], indent=2))
                        else:
                            f.write(json.dumps(msg['payload'], indent=2))
                        f.write("\n\n")
                    f.write("---\n\n")

                # Handle standalone RECEIVED messages
                elif msg['type'] == 'RECEIVED':
                    f.write(f"[{msg['timestamp']}] RECEIVED (CP -> Server): {msg['action']}\n")
                    if msg.get('full_ocpp_message'):
                        f.write(json.dumps(msg['full_ocpp_message'], indent=2))
                    else:
                        f.write(json.dumps(msg['payload'], indent=2))
                    f.write("\n\n---\n\n")

        logging.info(f"✅ {step_name} completed. Log written to: {log_file}")

        return jsonify({
            "status": f"Test step '{step_name}' completed for {charge_point_id}.",
            "log_file": log_file
        })

    except concurrent.futures.TimeoutError:
        logging.error(f"API call for '{step_name}' on {charge_point_id} timed out.")
        return jsonify({"error": f"Test step '{step_name}' timed out."}), 504
    except Exception as e:
        logging.exception("Error running test step")
        return jsonify({"error": f"Failed to run step '{step_name}': {e}"}), 500

@app.route("/api/test/get_configuration", methods=["POST"])
def get_configuration():
    """Call GetConfiguration and store results in CHARGE_POINTS."""
    active_charge_point_id = get_active_charge_point_id()

    if not active_charge_point_id:
        return jsonify({"error": "No active charge point selected."}), 400

    charge_point_id = active_charge_point_id

    if charge_point_id not in CHARGE_POINTS:
        return jsonify({"error": "Charge point not connected."}), 404

    ocpp_handler = CHARGE_POINTS.get(charge_point_id, {}).get("ocpp_handler")
    if not ocpp_handler:
        return jsonify({"error": "Charge point handler not found."}), 404

    if not app.loop or not app.loop.is_running():
        return jsonify({"error": "Server loop not available"}), 500

    async def call_get_configuration():
        """Call GetConfiguration and store the results."""
        from app.messages import GetConfigurationRequest

        logging.info("📋 Retrieving charge point configuration...")
        config_response = await ocpp_handler.send_and_wait(
            "GetConfiguration",
            GetConfigurationRequest(key=[]),
            timeout=OCPP_MESSAGE_TIMEOUT
        )

        # Store configuration in CHARGE_POINTS for log file
        if config_response and config_response.get("configurationKey"):
            config_dict = {}
            for config_item in config_response["configurationKey"]:
                key = config_item.get("key", "")
                value = config_item.get("value", "")
                readonly = config_item.get("readonly", False)

                if value:
                    config_dict[key] = f"{value} (RO)" if readonly else value
                else:
                    config_dict[key] = "No value" + (" (RO)" if readonly else "")

            # Add unknown keys
            if config_response.get("unknownKey"):
                for key in config_response["unknownKey"]:
                    config_dict[key] = "N/A (Not Supported)"

            CHARGE_POINTS[charge_point_id]["configuration_details"] = config_dict
            logging.info(f"✅ Retrieved {len(config_dict)} configuration keys")
            return {"success": True, "config_keys": len(config_dict)}
        else:
            logging.warning("⚠️ No configuration returned from charge point")
            return {"success": False, "error": "No configuration returned"}

    try:
        future = asyncio.run_coroutine_threadsafe(call_get_configuration(), app.loop)
        result = future.result(timeout=35)
        return jsonify(result), 200
    except Exception as e:
        logging.exception("Error calling GetConfiguration")
        return jsonify({"error": f"Failed to get configuration: {e}"}), 500

@app.route("/api/test/c_all_tests", methods=["POST"])
def run_c_all_tests():
    """C.1 and C.2 Tests - Run C.1 and C.2 tests sequentially and write comprehensive log to file."""
    import os
    from datetime import datetime
    from dataclasses import asdict, is_dataclass

    active_charge_point_id = get_active_charge_point_id()

    if not active_charge_point_id:
        return jsonify({"error": "No active charge point selected."}), 400

    charge_point_id = active_charge_point_id

    logging.info(f"API call to run C.1 and C.2 Tests for charge point '{charge_point_id}'")
    if charge_point_id not in CHARGE_POINTS:
        return jsonify({"error": "Charge point not connected."}), 404

    ocpp_handler = CHARGE_POINTS.get(charge_point_id, {}).get("ocpp_handler")
    if not ocpp_handler:
        return jsonify({"error": "Charge point handler not found. The charge point may not have fully booted."}), 404

    if ocpp_handler.test_lock.locked():
        return jsonify({"error": "A test is already running for this charge point."}), 429

    # Prepare log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = "/home/ocpp-tester/logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"c_all_tests_{charge_point_id}_{timestamp}.log")

    # Message log storage
    message_log = []

    # Define test name for filtering (C-series needs MeterValues, so won't filter them out)
    step_name = "c_all_tests"

    # Track triggered messages
    triggered_messages = set()

    def log_message(msg_type: str, action: str, payload: Any, timestamp_str: str, message_id: str = None, test_name: str = None):
        """Helper to log OCPP messages with full OCPP message format.

        Smart filtering:
        - A.6 test: Log ALL messages (complete OCPP trace needed)
        - C-series tests: Log ALL messages (needs MeterValues)
        - Other tests: Filter out Heartbeat, StatusNotification, MeterValues unless explicitly triggered
        - Always log REQUEST/RESPONSE (test-initiated actions)
        """
        # Convert dataclass to dict if needed
        if is_dataclass(payload):
            payload_dict = asdict(payload)
        elif isinstance(payload, dict):
            payload_dict = payload
        else:
            payload_dict = {"raw": str(payload)}

        # Build full OCPP message array
        if msg_type == "REQUEST":
            # CALL format: [2, message_id, action, payload]
            full_ocpp_message = [2, message_id, action, payload_dict]

            # Track if we're triggering StatusNotification or BootNotification
            if action == "TriggerMessage":
                requested_message = payload_dict.get("requestedMessage")
                if requested_message in ["StatusNotification", "BootNotification"]:
                    triggered_messages.add(requested_message)

        elif msg_type == "RESPONSE":
            # CALLRESULT format: [3, message_id, payload]
            full_ocpp_message = [3, message_id, payload_dict]
        elif msg_type == "RECEIVED":
            # CALL format from charge point: [2, message_id, action, payload]
            full_ocpp_message = [2, message_id, action, payload_dict]
        else:
            full_ocpp_message = None

        # Smart filtering for RECEIVED messages (from charge point)
        # C-series tests need MeterValues, so don't filter for them
        if msg_type == "RECEIVED":
            # A.6 or C-series tests: log ALL messages
            if test_name and ("a6" in test_name.lower() or "c_" in test_name.lower() or test_name.startswith("c")):
                pass  # Don't filter - log everything
            # Other tests: filter noise unless explicitly triggered
            elif action in ["Heartbeat", "StatusNotification", "MeterValues"]:
                # Don't log unless this message was explicitly triggered by the test
                if action not in triggered_messages:
                    return  # Skip logging this message
                # If it was triggered, log it and remove from triggered set
                triggered_messages.discard(action)

        message_log.append({
            "timestamp": timestamp_str,
            "type": msg_type,
            "action": action,
            "payload": payload_dict,
            "message_id": message_id,
            "full_ocpp_message": full_ocpp_message
        })

    # Wrap send_and_wait to capture messages
    original_send_and_wait = ocpp_handler.send_and_wait
    import uuid

    async def wrapped_send_and_wait(action: str, payload: Any, timeout: int = OCPP_MESSAGE_TIMEOUT):
        """Wrapper to log all OCPP requests and responses."""
        # Generate message ID (same as what send_and_wait will generate)
        message_id = str(uuid.uuid4())

        request_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_message("REQUEST", action, payload, request_timestamp, message_id, test_name=step_name)

        response = await original_send_and_wait(action, payload, timeout)

        response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # Check if timeout occurred (response is None)
        if response is None:
            log_message("RESPONSE_TIMEOUT", action, {"error": f"Timeout after {timeout}s - no response received from charge point"}, response_timestamp, message_id, test_name=step_name)
        else:
            log_message("RESPONSE", action, response, response_timestamp, message_id, test_name=step_name)

        return response

    async def run_tests_with_logging():
        """Run C.1 and C.2 tests with all charging rate values."""
        from app.core import get_charging_value
        from app.messages import GetConfigurationRequest

        async with ocpp_handler.test_lock:
            # Don't need status check for B/C tests - removed ensure_status_known call

            # Log the detected status as a manual entry
            status_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            cp_status = CHARGE_POINTS.get(charge_point_id, {}).get("status", "Unknown")
            message_log.append({
                "timestamp": status_timestamp,
                "type": "STATUS_DETECTED",
                "action": "StatusNotification",
                "payload": {"connectorId": 1, "status": cp_status},
                "message_id": None,
                "full_ocpp_message": None
            })

            # Now wrap send_and_wait for actual test messages
            ocpp_handler.send_and_wait = wrapped_send_and_wait

            try:
                ocpp_logic = ocpp_handler.ocpp_logic
                test_steps = ocpp_logic.test_steps

                # Get charge point configuration first
                logging.info("📋 Retrieving charge point configuration...")
                config_response = await ocpp_handler.send_and_wait(
                    "GetConfiguration",
                    GetConfigurationRequest(key=[]),
                    timeout=OCPP_MESSAGE_TIMEOUT
                )

                # Store configuration in CHARGE_POINTS for log file
                if config_response and config_response.get("configurationKey"):
                    config_dict = {}
                    for config_item in config_response["configurationKey"]:
                        key = config_item.get("key", "")
                        value = config_item.get("value", "")
                        readonly = config_item.get("readonly", False)

                        if value:
                            config_dict[key] = f"{value} (RO)" if readonly else value
                        else:
                            config_dict[key] = "No value" + (" (RO)" if readonly else "")

                    # Add unknown keys
                    if config_response.get("unknownKey"):
                        for key in config_response["unknownKey"]:
                            config_dict[key] = "N/A (Not Supported)"

                    CHARGE_POINTS[charge_point_id]["configuration_details"] = config_dict
                    logging.info(f"✅ Retrieved {len(config_dict)} configuration keys")

                # Test levels to iterate through
                test_levels = ["disable", "low", "medium", "high"]

                # Run C.1 test with all charging levels
                for level in test_levels:
                    value, unit = get_charging_value(level)
                    logging.info(f"📋 Starting C.1 test with {level} ({value}{unit})...")
                    await test_steps.run_c1_set_charging_profile_test(params={
                        "chargingRateUnit": unit,
                        "limit": value
                    })
                    await asyncio.sleep(2)

                # Run C.2 test with all charging levels
                for level in test_levels:
                    value, unit = get_charging_value(level)
                    logging.info(f"📋 Starting C.2 test with {level} ({value}{unit})...")
                    await test_steps.run_c2_tx_default_profile_test(params={
                        "chargingRateUnit": unit,
                        "limit": value
                    })
                    await asyncio.sleep(2)

            finally:
                # Restore original send_and_wait
                ocpp_handler.send_and_wait = original_send_and_wait

    try:
        # Run tests (4 charging levels × 2 tests = 8 test runs)
        future = asyncio.run_coroutine_threadsafe(run_tests_with_logging(), app.loop)
        future.result(timeout=480)  # 8 minutes timeout for all test iterations

        # Write comprehensive log file
        with open(log_file, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("OCPP 1.6J - C.1 and C.2 Tests - Comprehensive Log\n")
            f.write("All Charging Rate Values (disable, low, medium, high)\n")
            f.write("=" * 80 + "\n")
            f.write(f"Charge Point ID: {charge_point_id}\n")
            f.write(f"Test Start Time: {timestamp}\n")
            f.write(f"Server: OCPP Test Server\n")

            # Add connection status detection using the status we captured at test start
            # Find the STATUS_DETECTED entry in message_log
            detected_status = None
            for msg in message_log:
                if msg['type'] == 'STATUS_DETECTED':
                    detected_status = msg['payload']['status']
                    break

            # If we found detected status, use it; otherwise query current status
            if detected_status:
                from app.core import SERVER_SETTINGS
                ev_sim_available = SERVER_SETTINGS.get("ev_simulator_available", False)

                # If EV simulator is available, assume it's being used for testing
                if ev_sim_available:
                    connection_type = "EV Simulator"
                    details = f"Using EV simulator (Status: {detected_status})"
                elif detected_status in ["Preparing", "Charging", "SuspendedEV", "SuspendedEVSE", "Finishing"]:
                    connection_type = "Real EV Connected"
                    details = f"Real EV detected (Status: {detected_status})"
                elif detected_status == "Available":
                    connection_type = "No EV Connected"
                    details = "Charge point available, waiting for EV"
                elif detected_status == "Unavailable":
                    connection_type = "Charge Point Unavailable"
                    details = "Charge point is unavailable"
                elif detected_status == "Faulted":
                    connection_type = "Charge Point Faulted"
                    details = "Charge point has a fault condition"
                else:
                    connection_type = "Unknown"
                    details = f"Status: {detected_status or 'Not reported'}"

                f.write(f"Connection Type: {connection_type}\n")
                f.write(f"Details: {details}\n")
            else:
                # Fallback to querying current status if no STATUS_DETECTED entry found
                conn_status = get_connection_status(charge_point_id)
                f.write(f"Connection Type: {conn_status['type']}\n")
                f.write(f"Details: {conn_status['details']}\n")

            f.write("=" * 80 + "\n\n")

            import json

            # Extract and display test parameters at the top
            f.write("TEST PARAMETERS\n")
            f.write("=" * 80 + "\n")
            f.write("Test Levels: disable, low, medium, high\n")
            f.write("Tests Run: 8 total (4 C.1 iterations + 4 C.2 iterations)\n\n")

            # Extract SetChargingProfile requests to show actual parameters
            c1_requests = []
            c2_requests = []
            for msg in message_log:
                if msg['action'] == 'SetChargingProfile' and msg['type'] == 'REQUEST':
                    profile = msg['payload'].get('csChargingProfiles', {})
                    purpose = profile.get('chargingProfilePurpose', 'Unknown')
                    schedule = profile.get('chargingSchedule', {})
                    unit = schedule.get('chargingRateUnit', 'N/A')
                    periods = schedule.get('chargingSchedulePeriod', [])
                    limit = periods[0].get('limit') if periods else 'N/A'

                    param_info = {
                        'connectorId': msg['payload'].get('connectorId'),
                        'purpose': purpose,
                        'stackLevel': profile.get('stackLevel', 0),
                        'kind': profile.get('chargingProfileKind', 'N/A'),
                        'unit': unit,
                        'limit': limit,
                        'duration': schedule.get('duration', 'N/A'),
                        'numberPhases': periods[0].get('numberPhases') if periods else 'N/A'
                    }

                    if purpose == 'TxProfile':
                        c1_requests.append(param_info)
                    elif purpose == 'TxDefaultProfile':
                        c2_requests.append(param_info)

            # Display C.1 parameters
            f.write("C.1 Test (TxProfile) Parameters:\n")
            f.write("-" * 80 + "\n")
            for i, params in enumerate(c1_requests, 1):
                f.write(f"Iteration {i}:\n")
                f.write(f"  Connector ID: {params['connectorId']}\n")
                f.write(f"  Stack Level: {params['stackLevel']}\n")
                f.write(f"  Profile Kind: {params['kind']}\n")
                f.write(f"  Charging Rate Unit: {params['unit']}\n")
                f.write(f"  Power Limit: {params['limit']} {params['unit']}\n")
                f.write(f"  Duration: {params['duration']} seconds\n")
                f.write(f"  Number of Phases: {params['numberPhases']}\n\n")

            # Display C.2 parameters
            f.write("C.2 Test (TxDefaultProfile) Parameters:\n")
            f.write("-" * 80 + "\n")
            for i, params in enumerate(c2_requests, 1):
                f.write(f"Iteration {i}:\n")
                f.write(f"  Connector ID: {params['connectorId']}\n")
                f.write(f"  Stack Level: {params['stackLevel']}\n")
                f.write(f"  Profile Kind: {params['kind']}\n")
                f.write(f"  Charging Rate Unit: {params['unit']}\n")
                f.write(f"  Power Limit: {params['limit']} {params['unit']}\n")
                f.write(f"  Duration: {params['duration']}\n")
                f.write(f"  Number of Phases: {params['numberPhases']}\n\n")

            f.write("=" * 80 + "\n\n")

            # Get test results
            test_results = CHARGE_POINTS[charge_point_id].get("test_results", {})
            c1_result = test_results.get("run_c1_set_charging_profile_test", "NOT RUN")
            c2_result = test_results.get("run_c2_tx_default_profile_test", "NOT RUN")

            f.write("TEST RESULTS\n")
            f.write(f"C.1: {c1_result}\n")
            f.write(f"C.2: {c2_result}\n")
            f.write("-" * 80 + "\n\n")

            # Get verification results if available
            if charge_point_id in VERIFICATION_RESULTS:
                f.write("VERIFICATION RESULTS\n")
                f.write("-" * 80 + "\n")
                import json
                f.write(json.dumps(VERIFICATION_RESULTS[charge_point_id], indent=2))
                f.write("\n" + "-" * 80 + "\n\n")

            # Write all OCPP messages
            f.write("OCPP MESSAGE LOG\n")
            f.write("=" * 80 + "\n\n")

            # If no messages, add explanation (shouldn't happen for C tests, but handle it)
            if not message_log:
                f.write("ℹ️  No OCPP messages were sent during this test\n")
                f.write("=" * 80 + "\n\n")

            import json
            for msg in message_log:
                # Skip STATUS_DETECTED messages - don't log them
                if msg['type'] == 'STATUS_DETECTED':
                    continue

                # For REQUEST: show action and description
                # For RECEIVED: show action (message from charge point)
                # For RESPONSE_TIMEOUT: show error message
                # For RESPONSE: only show timestamp and type
                if msg['type'] == 'REQUEST':
                    # Add specific details for certain actions
                    if msg['action'] == 'TriggerMessage' and 'requestedMessage' in msg['payload']:
                        req_msg = msg['payload']['requestedMessage']
                        f.write(f"[{msg['timestamp']}] {msg['type']}: Trigger {req_msg}\n")
                    elif msg['action'] == 'ChangeConfiguration' and 'key' in msg['payload']:
                        key_name = msg['payload']['key']
                        f.write(f"[{msg['timestamp']}] {msg['type']}: {key_name}\n")
                    else:
                        f.write(f"[{msg['timestamp']}] {msg['type']}: {msg['action']}\n")
                elif msg['type'] == 'RECEIVED':
                    f.write(f"[{msg['timestamp']}] {msg['type']}: {msg['action']}\n")
                elif msg['type'] == 'RESPONSE_TIMEOUT':
                    f.write(f"[{msg['timestamp']}] ⏱️  TIMEOUT ERROR\n")
                    f.write(f"ERROR: {msg['payload'].get('error', 'Timeout occurred')}\n")
                else:
                    f.write(f"[{msg['timestamp']}] {msg['type']}\n")

                # Write message details
                f.write("-" * 80 + "\n")
                # Write full OCPP message if available, otherwise just payload
                if msg.get('full_ocpp_message'):
                    f.write(json.dumps(msg['full_ocpp_message'], indent=2))
                else:
                    f.write(json.dumps(msg['payload'], indent=2))
                f.write("\n" + "=" * 80 + "\n\n")

        logging.info(f"✅ C.1 and C.2 Tests completed. Log written to: {log_file}")

        return jsonify({
            "status": f"C.1 and C.2 Tests completed for {charge_point_id}",
            "log_file": log_file,
            "test_results": {
                "c1": c1_result,
                "c2": c2_result
            }
        })

    except concurrent.futures.TimeoutError:
        logging.error(f"API call for 'C.1 and C.2 Tests' on {charge_point_id} timed out.")
        return jsonify({"error": "C.1 and C.2 Tests timed out."}), 504
    except Exception as e:
        logging.exception("Error running C.1 and C.2 Tests")
        return jsonify({"error": f"Failed to run C.1 and C.2 Tests: {e}"}), 500

@app.route("/api/test/get_latest_log", methods=["GET"])
def get_latest_log():
    """Get the latest log file for a specific test."""
    import os
    import glob

    test_name = request.args.get('test_name')
    if not test_name:
        return jsonify({"error": "test_name parameter required"}), 400

    active_charge_point_id = get_active_charge_point_id()
    if not active_charge_point_id:
        return jsonify({"error": "No active charge point"}), 400

    log_dir = "/home/ocpp-tester/logs"
    pattern = f"{log_dir}/{test_name}_{active_charge_point_id}_*.log"

    log_files = glob.glob(pattern)
    if not log_files:
        return jsonify({"error": f"No log files found for {test_name}"}), 404

    # Get the most recent log file
    latest_log = max(log_files, key=os.path.getmtime)

    return jsonify({"log_file": latest_log})

@app.route("/api/test/combine_logs", methods=["POST"])
def combine_logs():
    """Combine multiple log files into one comprehensive log."""
    import os
    from datetime import datetime

    data = request.get_json(silent=True) or {}
    log_files = data.get('log_files', [])
    test_name = data.get('test_name', 'combined_tests')

    if not log_files:
        return jsonify({"error": "No log files provided"}), 400

    active_charge_point_id = get_active_charge_point_id()
    if not active_charge_point_id:
        return jsonify({"error": "No active charge point"}), 400

    # Create combined log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = "/home/ocpp-tester/logs"
    os.makedirs(log_dir, exist_ok=True)
    combined_log_file = os.path.join(log_dir, f"{test_name}_{active_charge_point_id}_{timestamp}.log")

    try:
        with open(combined_log_file, "w") as outfile:
            outfile.write("=" * 80 + "\n")
            outfile.write(f"OCPP 1.6J - {test_name.upper()} - Combined Comprehensive Log\n")
            outfile.write("=" * 80 + "\n")
            outfile.write(f"Charge Point ID: {active_charge_point_id}\n")
            outfile.write(f"Combined Log Created: {timestamp}\n")
            outfile.write(f"Number of Individual Tests: {len(log_files)}\n")
            outfile.write("=" * 80 + "\n\n")

            # Append each log file
            for idx, log_file in enumerate(log_files, 1):
                if not os.path.exists(log_file):
                    outfile.write(f"WARNING: Log file not found: {log_file}\n\n")
                    continue

                outfile.write("\n" + "=" * 80 + "\n")
                outfile.write(f"TEST #{idx}: {os.path.basename(log_file)}\n")
                outfile.write("=" * 80 + "\n\n")

                with open(log_file, "r") as infile:
                    outfile.write(infile.read())

                outfile.write("\n\n")

        logging.info(f"✅ Combined log file created: {combined_log_file}")

        return jsonify({
            "status": "success",
            "combined_log_file": combined_log_file,
            "individual_logs": log_files
        })

    except Exception as e:
        logging.exception("Error combining log files")
        return jsonify({"error": f"Failed to combine logs: {e}"}), 500

@app.route("/api/rfid_status")
def get_rfid_status():
    """Get current RFID test status for real-time updates in the UI."""
    try:
        from app.ocpp_message_handlers import rfid_test_state
        return jsonify({
            "active": rfid_test_state["active"],
            "cards_presented": rfid_test_state["cards_presented"],
            "test_start_time": rfid_test_state["test_start_time"].isoformat() if rfid_test_state["test_start_time"] else None
        })
    except Exception as e:
        logging.exception("Error getting RFID status")
        return jsonify({"error": f"Failed to get RFID status: {e}"}), 500

@app.route("/api/enable_rfid_test_mode", methods=["POST"])
def enable_rfid_test_mode():
    """Enable RFID test mode to accept any card and clear accepted_rfid."""
    try:
        from app.ocpp_message_handlers import rfid_test_state
        rfid_test_state["active"] = True
        rfid_test_state["cards_presented"] = []

        # Clear accepted_rfid for active charge point so any card tap is detected as new
        active_cp_id = get_active_charge_point_id()
        if active_cp_id and active_cp_id in CHARGE_POINTS:
            CHARGE_POINTS[active_cp_id]["accepted_rfid"] = None
            logging.info(f"🔄 Cleared accepted_rfid for {active_cp_id} to detect new card taps")

        logging.info("🔓 RFID test mode enabled via API - any card will be accepted")
        return jsonify({
            "status": "success",
            "message": "RFID test mode enabled"
        })
    except Exception as e:
        logging.exception("Error enabling RFID test mode")
        return jsonify({"error": f"Failed to enable RFID test mode: {e}"}), 500

@app.route("/api/disable_rfid_test_mode", methods=["POST"])
def disable_rfid_test_mode():
    """Disable RFID test mode."""
    try:
        from app.ocpp_message_handlers import rfid_test_state
        rfid_test_state["active"] = False
        rfid_test_state["cards_presented"] = []
        logging.info("🔒 RFID test mode disabled via API")
        return jsonify({
            "status": "success",
            "message": "RFID test mode disabled"
        })
    except Exception as e:
        logging.exception("Error disabling RFID test mode")
        return jsonify({"error": f"Failed to disable RFID test mode: {e}"}), 500

@app.route("/api/clear_test_results", methods=["POST"])
def clear_test_results():
    """Clear all test results for all charge points."""
    try:
        cleared_count = 0
        for cp_id, cp_data in CHARGE_POINTS.items():
            if "test_results" in cp_data:
                cp_data["test_results"] = {}
                cleared_count += 1

        logging.info(f"🧹 Cleared test results for {cleared_count} charge point(s)")
        return jsonify({
            "status": "success",
            "message": f"Cleared test results for {cleared_count} charge point(s)",
            "cleared_count": cleared_count
        })
    except Exception as e:
        logging.exception("Error clearing test results")
        return jsonify({"error": f"Failed to clear test results: {e}"}), 500

@app.route("/api/verification_results", methods=["GET"])
def get_verification_results():
    """Get verification results for the active charge point."""
    try:
        active_cp_id = get_active_charge_point_id()
        if not active_cp_id:
            return jsonify({"error": "No active charge point selected"}), 400

        # Check if specific test requested via query param
        test_param = request.args.get('test', '').upper()  # C1 or C2

        if test_param:
            # Return specific test results
            key = f"{active_cp_id}_{test_param}"
            if key not in VERIFICATION_RESULTS:
                return jsonify({"error": f"No verification results available for {test_param}"}), 404
            return jsonify(VERIFICATION_RESULTS[key])
        else:
            # Return all verification results for this charge point
            cp_results = {k: v for k, v in VERIFICATION_RESULTS.items() if k.startswith(f"{active_cp_id}_")}
            if not cp_results:
                return jsonify({"error": "No verification results available"}), 404
            return jsonify(cp_results)
    except Exception as e:
        logging.exception("Error getting verification results")
        return jsonify({"error": f"Failed to get verification results: {e}"}), 500
