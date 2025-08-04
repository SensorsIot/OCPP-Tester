"""
This module contains the client-side logic for the Central System.
It is responsible for sending OCPP requests to the Charge Point.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Tuple
from websockets.client import connect, WebSocketClientProtocol

# Corrected import path to reference the messages module within the same app directory
from .messages import (
    ChangeAvailabilityRequest,
    ChangeAvailabilityResponse,
    GetConfigurationRequest,
    TriggerMessageRequest,
    ChangeConfigurationRequest,
    GetCompositeScheduleRequest,
)

# Configure logging for this script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def send_ocpp_call(
    websocket: WebSocketClientProtocol, action: str, payload: Any
) -> Tuple[str, Any]:
    """
    Sends an OCPP CALL (request) message and logs the response.
    """
    unique_id = str(uuid.uuid4())
    message_type_id = 2  # CALL

    message = json.dumps([message_type_id, unique_id, action, payload.__dict__])
    await websocket.send(message)
    logger.info(f"Sent CALL for '{action}' with ID '{unique_id}'")
    logger.debug(f"Payload: {payload.__dict__}")
    
    # Wait for a response with the same unique ID
    async for response_message in websocket:
        response_array = json.loads(response_message)
        response_unique_id = response_array[1]
        
        if response_unique_id == unique_id:
            logger.info(f"Received response for '{action}' with ID '{unique_id}'")
            logger.debug(f"Response: {response_array}")
            return response_unique_id, response_array
            
    return unique_id, None

async def run_client_task(charge_point_id: str, wallbox_url: str):
    """
    Connects to the Wallbox and sends a sequence of commands.
    """
    try:
        async with connect(f"{wallbox_url}/{charge_point_id}") as websocket:
            logger.info("Client connected to Wallbox. Starting command sequence...")
            
            # 1. ChangeAvailability
            await send_ocpp_call(websocket, "ChangeAvailability", ChangeAvailabilityRequest(connectorId=0, type="Operative"))

            # 2. GetConfiguration
            await send_ocpp_call(websocket, "GetConfiguration", GetConfigurationRequest())

            # 3. TriggerMessage for BootNotification
            await send_ocpp_call(websocket, "TriggerMessage", TriggerMessageRequest(requestedMessage="BootNotification"))

            # 4. ChangeConfiguration for MeterValuesSampledData (repeated multiple times in log)
            await send_ocpp_call(websocket, "ChangeConfiguration", ChangeConfigurationRequest(key="MeterValuesSampledData", value="Power.Active.Import"))
            await send_ocpp_call(websocket, "ChangeConfiguration", ChangeConfigurationRequest(key="MeterValuesSampledData", value="Energy.Active.Import.Register"))
            await send_ocpp_call(websocket, "ChangeConfiguration", ChangeConfigurationRequest(key="MeterValuesSampledData", value="Current.Import"))
            await send_ocpp_call(websocket, "ChangeConfiguration", ChangeConfigurationRequest(key="MeterValuesSampledData", value="Voltage"))
            await send_ocpp_call(websocket, "ChangeConfiguration", ChangeConfigurationRequest(key="MeterValuesSampledData", value="Current.Offered"))
            await send_ocpp_call(websocket, "ChangeConfiguration", ChangeConfigurationRequest(key="MeterValuesSampledData", value="Power.Offered"))
            await send_ocpp_call(websocket, "ChangeConfiguration", ChangeConfigurationRequest(key="MeterValuesSampledData", value="SoC"))
            await send_ocpp_call(websocket, "ChangeConfiguration", ChangeConfigurationRequest(key="MeterValuesSampledData", value="Power.Active.Import,Energy.Active.Import.Register,Current.Import,Voltage,Current.Offered,Power.Offered,SoC"))
            
            # 5. ChangeConfiguration for MeterValueSampleInterval
            await send_ocpp_call(websocket, "ChangeConfiguration", ChangeConfigurationRequest(key="MeterValueSampleInterval", value="10"))

            # 6. ChangeConfiguration for WebSocketPingInterval
            await send_ocpp_call(websocket, "ChangeConfiguration", ChangeConfigurationRequest(key="WebSocketPingInterval", value="30"))

            # 7. TriggerMessage for StatusNotification
            await send_ocpp_call(websocket, "TriggerMessage", TriggerMessageRequest(requestedMessage="StatusNotification"))

            # 8. TriggerMessage for MeterValues with connectorId
            await send_ocpp_call(websocket, "TriggerMessage", TriggerMessageRequest(requestedMessage="MeterValues", connectorId=1))

            # 9. TriggerMessage for StatusNotification with connectorId
            await send_ocpp_call(websocket, "TriggerMessage", TriggerMessageRequest(requestedMessage="StatusNotification", connectorId=1))

            # 10. GetCompositeSchedule
            await send_ocpp_call(websocket, "GetCompositeSchedule", GetCompositeScheduleRequest(connectorId=1, duration=60))
            
            logger.info("Client command sequence sent. Client is now closing connection.")
            
    except ConnectionRefusedError:
        logger.error("Client connection refused. Make sure the Wallbox's server is active.")
    except Exception as e:
        logger.error(f"An unexpected client error occurred: {e}")

