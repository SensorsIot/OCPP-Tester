"""
OCPPHandler: manages a single WebSocket connection to a charge point.
Maps OCPP actions (from the Charge Point to Central System) to
their async handler functions and payload dataclasses.
"""
import asyncio
import json
import logging
import uuid
from dataclasses import asdict, is_dataclass, fields, is_dataclass as is_dc
from typing import Any, Dict, Type, Callable

from app.messages import (
    BootNotificationRequest, AuthorizeRequest, DataTransferRequest,
    StatusNotificationRequest, FirmwareStatusNotificationRequest,
    DiagnosticsStatusNotificationRequest, HeartbeatRequest,
    StartTransactionRequest, StopTransactionRequest, MeterValuesRequest,
    TriggerMessageRequest,
)
from app.ocpp_server_logic import OcppServerLogic
from app.state import CHARGE_POINTS
from websockets.server import ServerConnection
from websockets.exceptions import ConnectionClosedOK

logger = logging.getLogger(__name__)

# Each entry: action -> {"handler": async function, "payload_class": dataclass}
MESSAGE_HANDLERS: Dict[str, Dict[str, Any]] = {
    "BootNotification": {
        "handler_name": "handle_boot_notification",
        "payload_class": BootNotificationRequest,
    },
    "Authorize": {
        "handler_name": "handle_authorize",
        "payload_class": AuthorizeRequest,
    },
    "DataTransfer": {
        "handler_name": "handle_data_transfer",
        "payload_class": DataTransferRequest,
    },
    "StatusNotification": {
        "handler_name": "handle_status_notification",
        "payload_class": StatusNotificationRequest,
    },
    "FirmwareStatusNotification": {
        "handler_name": "handle_firmware_status_notification",
        "payload_class": FirmwareStatusNotificationRequest,
    },
    "DiagnosticsStatusNotification": {
        "handler_name": "handle_diagnostics_status_notification",
        "payload_class": DiagnosticsStatusNotificationRequest,
    },
    "Heartbeat": {
        "handler_name": "handle_heartbeat",
        "payload_class": HeartbeatRequest,
    },
    "StartTransaction": {
        "handler_name": "handle_start_transaction",
        "payload_class": StartTransactionRequest,
    },
    "StopTransaction": {
        "handler_name": "handle_stop_transaction",
        "payload_class": StopTransactionRequest,
    },
    "MeterValues": {
        "handler_name": "handle_meter_values",
        "payload_class": MeterValuesRequest,
    },
}

# Optional: safe fallback if some vendor sends an action we don't support.
async def handle_unknown_action(charge_point_id: str, payload: dict):
    logger.warning(f"Unknown/unsupported action for {charge_point_id}: {payload}")
    return None

def create_ocpp_message(message_type_id: int, unique_id: str, payload: Any, action: str = None) -> str:
    dict_factory = lambda data: {k: v for (k, v) in data if v is not None}
    payload_to_send = asdict(payload, dict_factory=dict_factory) if is_dataclass(payload) else payload
    if action:
        message = [message_type_id, unique_id, action, payload_to_send]
    else:
        message = [message_type_id, unique_id, payload_to_send]
    logger.debug("\n\n------------OCPP Call----------")
    return json.dumps(message)

def _filter_payload(payload_cls: Type, data: Dict) -> Dict:
    if not is_dc(payload_cls):
        return data
    allowed = {f.name for f in fields(payload_cls)}
    return {k: v for k, v in data.items() if k in allowed}

class OCPPHandler:
    def __init__(self, websocket: ServerConnection, path: str, refresh_trigger: asyncio.Event = None):
        self.websocket = websocket
        self.path = path
        self.charge_point_id = path.strip("/")
        self.pending_requests: Dict[str, Dict[str, Any]] = {}
        self.refresh_trigger = refresh_trigger
        self.ocpp_logic = OcppServerLogic(self, self.refresh_trigger)
        self._logic_task = None

    async def start(self):
        if not self.charge_point_id:
            logger.warning("Connection closed: missing Charge Point ID in path.")
            await self.websocket.close()
            return

        CHARGE_POINTS[self.charge_point_id] = {"ocpp_handler": self}
        logger.info(f"New connection from Charge Point: {self.charge_point_id}")

        self._logic_task = asyncio.create_task(self.run_logic_and_periodic_tasks())
        logger.info(f"Main logic task for {self.charge_point_id} started.")

        try:
            async for message in self.websocket:
                await self.process_message(message)
        finally:
            logger.info(f"Connection with {self.charge_point_id} closing. Cancelling logic task.")
            if self._logic_task:
                self._logic_task.cancel()
                try:
                    await self._logic_task
                except asyncio.CancelledError:
                    logger.info(f"Logic task for {self.charge_point_id} cancelled.")
            CHARGE_POINTS.pop(self.charge_point_id, None)
            logger.info(f"Cleaned up state for {self.charge_point_id}.")

    async def run_logic_and_periodic_tasks(self):
        try:
            # The server is now fully driven by the UI for running test steps.
            # This task's only responsibility is to start the passive,
            # long-running health check loop that waits for heartbeats.
            logger.info(f"Connection for {self.charge_point_id} established. Starting periodic health checks.")
            await self.ocpp_logic.periodic_health_checks()
        except asyncio.CancelledError:
            logger.info(f"Logic task for {self.charge_point_id} cancelled.")
        except ConnectionClosedOK:
            logger.info(f"Connection closed during logic task for {self.charge_point_id}.")
        except Exception as e:
            logger.error(f"Logic error for {self.charge_point_id}: {e}", exc_info=True)

    async def send_and_wait(self, action: str, request_payload: Any, timeout: int = 30) -> bool:
        unique_id = str(uuid.uuid4())
        event = asyncio.Event()
        self.pending_requests[unique_id] = {"action": action, "event": event}
        message = create_ocpp_message(2, unique_id, request_payload, action)
        await self.websocket.send(message)
        logger.info(f"Sent {action} (id={unique_id}). Waiting for response...")
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            logger.info(f"Response received for {action} (id={unique_id}). Proceeding.")
            return True
        except asyncio.TimeoutError:
            logger.error(f"Timeout: No response for {action} (id={unique_id}) within {timeout}s.")
            return False
        finally:
            self.pending_requests.pop(unique_id, None)

    async def process_message(self, raw: str):
        try:
            msg = json.loads(raw)
            message_type_id, unique_id = msg[0], msg[1]
        except (json.JSONDecodeError, IndexError) as e:
            logger.error(f"Failed to parse OCPP message: {raw}, error: {e}")
            return

        if message_type_id == 2:  # CALL
            action, payload_dict = msg[2], msg[3]
            await self.handle_call(unique_id, action, payload_dict)
        elif message_type_id == 3:  # CALLRESULT
            payload = msg[2]
            await self.handle_call_result(unique_id, payload)
        elif message_type_id == 4:  # CALLERROR
            errorCode, errorDescription, details = msg[2], msg[3], msg[4] if len(msg) > 4 else {}
            await self.handle_call_error(unique_id, errorCode, errorDescription, details)
        else:
            logger.warning(f"Unknown OCPP message type {message_type_id} from {self.charge_point_id}")

    async def handle_call(self, unique_id: str, action: str, payload_dict: Dict):
        logger.debug(f"Received CALL '{action}' from {self.charge_point_id}")
        handler_info = MESSAGE_HANDLERS.get(action)
        if not handler_info:
            logger.warning(f"No handler registered for action '{action}'")
            return
        handler_name, payload_class = handler_info["handler_name"], handler_info["payload_class"]
        try:
            filtered = _filter_payload(payload_class, payload_dict)
            handler = getattr(self.ocpp_logic, handler_name)
            payload = payload_class(**filtered)
            response_payload = await handler(self.charge_point_id, payload)
            if response_payload is not None:
                response_message = create_ocpp_message(3, unique_id, response_payload)
                await self.websocket.send(response_message)
                logger.info(f"Sent response for '{action}' to {self.charge_point_id}")
        except TypeError as e:
            logger.error(f"Payload validation failed for '{action}': {e}")
            error = [4, unique_id, "FormationViolation", str(e), {}]
            await self.websocket.send(json.dumps(error))
        except Exception as e:
            logger.error(f"Error handling '{action}': {e}", exc_info=True)
            error = [4, unique_id, "InternalError", str(e), {}]
            await self.websocket.send(json.dumps(error))

    async def handle_call_result(self, unique_id: str, payload: Dict):
        """Handle a CALLRESULT message from the charge point."""
        if unique_id in self.pending_requests:
            request_info = self.pending_requests[unique_id]
            action = request_info.get("action", "unknown action")
            logger.info(f"Received CALLRESULT for '{action}' (id={unique_id}) from {self.charge_point_id}")
            if action == "GetConfiguration":
                logger.info(f"  -> GetConfiguration response payload: {payload}")
            event = request_info.get("event")
            if event:
                event.set()
        else:
            logger.warning(f"Received unsolicited CALLRESULT with id {unique_id} from {self.charge_point_id}")

    async def handle_call_error(self, unique_id: str, error_code: str, error_description: str, details: Dict):
        """Handle a CALLERROR message from the charge point."""
        if unique_id in self.pending_requests:
            request_info = self.pending_requests[unique_id]
            action = request_info.get("action", "unknown action")
            logger.error(
                f"Received CALLERROR for '{action}' (id={unique_id}) from {self.charge_point_id}: "
                f"[{error_code}] {error_description} - Details: {details}"
            )
            event = request_info.get("event")
            if event:
                event.set()
