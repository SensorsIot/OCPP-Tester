"""
This module defines Python classes that represent the JSON payloads for
OCPP 1.6-J messages, as described in the provided documents.

Using classes for message payloads provides structure, type hinting, and
validation, which is crucial for a robust server implementation.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

@dataclass
class BootNotificationRequest:
    """
    Represents the payload for a BootNotification.req message.
    """
    chargePointVendor: str
    chargePointModel: str
    chargeBoxSerialNumber: Optional[str] = None
    chargePointSerialNumber: Optional[str] = None
    firmwareVersion: Optional[str] = None
    iccid: Optional[str] = None
    imsi: Optional[str] = None
    meterSerialNumber: Optional[str] = None
    meterType: Optional[str] = None

@dataclass
class BootNotificationResponse:
    """
    Represents the payload for a BootNotification.conf message.
    """
    status: str # "Accepted", "Pending", "Rejected"
    currentTime: str # ISO 8601 timestamp
    interval: int # Heartbeat interval in seconds

@dataclass
class AuthorizeRequest:
    """
    Represents the payload for an Authorize.req message.
    """
    idTag: str

@dataclass
class IdTagInfo:
    """
    A nested object in the Authorize.conf, StartTransaction.conf,
    and StopTransaction.conf payloads.
    """
    status: str # "Accepted", "Blocked", "Expired", "Invalid", "ConcurrentTx"
    expiryDate: Optional[str] = None
    parentIdTag: Optional[str] = None

@dataclass
class AuthorizeResponse:
    """
    Represents the payload for an Authorize.conf message.
    """
    idTagInfo: IdTagInfo # Must contain a "status" key

@dataclass
class DataTransferRequest:
    """
    Represents the payload for a DataTransfer.req message.
    """
    vendorId: str
    messageId: Optional[str] = None
    data: Optional[Any] = None

@dataclass
class DataTransferResponse:
    """
    Represents the payload for a DataTransfer.conf message.
    """
    status: str # "Accepted", "Rejected", "UnknownVendorId", "UnknownMessageId"
    data: Optional[Any] = None
    
@dataclass
class StatusNotificationRequest:
    """
    Represents the payload for a StatusNotification.req message.
    
    This class has been updated to handle unexpected keyword arguments,
    such as the 'info' key from your wallbox, without raising an error.
    """
    connectorId: int
    errorCode: str
    status: str
    timestamp: Optional[str] = None
    vendorId: Optional[str] = None
    vendorErrorCode: Optional[str] = None
    # Add 'info' field to correctly capture the incoming value
    info: Optional[str] = None
    # Use a post-init method to handle other extra vendor-specific fields
    extra_fields: Dict[str, Any] = field(init=False, default_factory=dict)

    def __post_init__(self, **kwargs):
        self.extra_fields = kwargs

@dataclass
class StatusNotificationResponse:
    """
    Represents the payload for a StatusNotification.conf message.
    """
    # This message has no payload, so the class is empty.
    pass

# ---- New Payloads for Server-Initiated Commands (and their responses) ----

@dataclass
class ChangeAvailabilityRequest:
    """
    Represents the payload for a ChangeAvailability.req message.
    """
    connectorId: int
    type: str # "Inoperative" or "Operative"

@dataclass
class ChangeAvailabilityResponse:
    """
    Represents the payload for a ChangeAvailability.conf message.
    """
    status: str # "Accepted", "Rejected", "Scheduled"

@dataclass
class ConfigurationKey:
    """
    A nested object in the GetConfiguration.conf payload.
    """
    key: str
    readonly: bool
    value: Optional[str] = None

@dataclass
class GetConfigurationRequest:
    """
    Represents the payload for a GetConfiguration.req message.
    """
    key: Optional[List[str]] = None

@dataclass
class GetConfigurationResponse:
    """
    Represents the payload for a GetConfiguration.conf message.
    """
    configurationKey: List[ConfigurationKey]
    unknownKey: Optional[List[str]] = None

@dataclass
class ChangeConfigurationRequest:
    """
    Represents the payload for a ChangeConfiguration.req message.
    """
    key: str
    value: str

@dataclass
class ChangeConfigurationResponse:
    """
    Represents the payload for a ChangeConfiguration.conf message.
    """
    status: str # "Accepted", "Rejected", "NotSupported", "RebootRequired"

@dataclass
class TriggerMessageRequest:
    """
    Represents the payload for a TriggerMessage.req message.
    """
    requestedMessage: str
    connectorId: Optional[int] = None

@dataclass
class TriggerMessageResponse:
    """
    Represents the payload for a TriggerMessage.conf message.
    """
    status: str # "Accepted", "Rejected", "NotImplemented"

@dataclass
class SampledValue:
    """
    A nested object within a MeterValues.req payload.
    """
    value: str
    context: Optional[str] = None
    format: Optional[str] = None
    measurand: Optional[str] = None
    location: Optional[str] = None
    unit: Optional[str] = None
    phase: Optional[str] = None

@dataclass
class MeterValue:
    """
    A nested object within a MeterValues.req payload.
    """
    timestamp: str
    sampledValue: List[SampledValue]

@dataclass
class MeterValuesRequest:
    """
    Represents the payload for a MeterValues.req message.
    """
    connectorId: int
    meterValue: List[MeterValue]
    transactionId: Optional[int] = None

@dataclass
class MeterValuesResponse:
    """
    Represents the payload for a MeterValues.conf message.
    """
    # This message has no payload.
    pass

@dataclass
class GetCompositeScheduleRequest:
    """
    Represents the payload for a GetCompositeSchedule.req message.
    """
    connectorId: int
    duration: int
    chargingRateUnit: Optional[str] = None

@dataclass
class ChargingSchedulePeriod:
    """
    A nested object in the GetCompositeSchedule.conf payload.
    """
    startPeriod: int
    limit: float
    numberPhases: Optional[int] = None

@dataclass
class ChargingSchedule:
    """
    A nested object in the GetCompositeSchedule.conf payload.
    
    This class has been updated to fix the non-default argument order.
    """
    chargingRateUnit: str
    chargingSchedulePeriod: List[ChargingSchedulePeriod]
    duration: Optional[int] = None
    startSchedule: Optional[str] = None
    minChargingRate: Optional[float] = None

@dataclass
class GetCompositeScheduleResponse:
    """
    Represents the payload for a GetCompositeSchedule.conf message.
    """
    status: str # "Accepted", "Rejected"
    connectorId: int
    scheduleStart: Optional[str] = None
    chargingSchedule: Optional[ChargingSchedule] = None

@dataclass
class HeartbeatRequest:
    """
    Represents the payload for a Heartbeat.req message.
    As per the specification, this message has no payload.
    """
    pass

@dataclass
class HeartbeatResponse:
    """
    Represents the payload for a Heartbeat.conf message.
    """
    currentTime: str

@dataclass
class StartTransactionRequest:
    """
    Represents the payload for a StartTransaction.req message.
    """
    connectorId: int
    idTag: str
    meterStart: int
    timestamp: str
    reservationId: Optional[int] = None

@dataclass
class StartTransactionResponse:
    """
    Represents the payload for a StartTransaction.conf message.
    """
    idTagInfo: IdTagInfo
    transactionId: int

@dataclass
class StopTransactionRequest:
    """
    Represents the payload for a StopTransaction.req message.
    """
    meterStop: int
    timestamp: str
    transactionId: int
    idTag: Optional[str] = None
    reason: Optional[str] = None
    transactionData: Optional[List[MeterValue]] = None

@dataclass
class StopTransactionResponse:
    """
    Represents the payload for a StopTransaction.conf message.
    """
    idTagInfo: Optional[IdTagInfo] = None
