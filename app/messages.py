"""
This module defines Python classes that represent the JSON payloads for
OCPP 1.6-J messages, as described in the provided documents.

Using classes for message payloads provides structure, type hinting, and
validation, which is crucial for a robust server implementation.
"""

from typing import Dict, Any, List, Optional, Union
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

    def __post_init__(self):
        # The JSON library decodes to dicts. We need to convert the nested dict
        # into an IdTagInfo object for type safety and easier access.
        if self.idTagInfo and isinstance(self.idTagInfo, dict):
            self.idTagInfo = IdTagInfo(**self.idTagInfo)


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

    def __post_init__(self, **kwargs):
        self.extra_fields = kwargs

@dataclass
class StatusNotificationResponse:
    """
    Represents the payload for a StatusNotification.conf message.
    """
    # This message has no payload, so the class is empty.
    pass

@dataclass
class FirmwareStatusNotificationRequest:
    """
    Represents the payload for a FirmwareStatusNotification.req message.
    """
    status: str # "Downloaded", "DownloadFailed", "Downloading", "Idle", "InstallationFailed", "Installed", "Installing"

@dataclass
class FirmwareStatusNotificationResponse:
    """
    Represents the payload for a FirmwareStatusNotification.conf message.
    """
    # This message has no payload.
    pass

@dataclass
class DiagnosticsStatusNotificationRequest:
    """
    Represents the payload for a DiagnosticsStatusNotification.req message.
    """
    status: str # "Idle", "Uploaded", "UploadFailed", "Uploading"

@dataclass
class DiagnosticsStatusNotificationResponse:
    """
    Represents the payload for a DiagnosticsStatusNotification.conf message.
    """
    # This message has no payload.
    pass

@dataclass
class HeartbeatRequest:
    """
    Represents the payload for a Heartbeat.req message.
    """
    # This message has no payload.
    pass

@dataclass
class HeartbeatResponse:
    """
    Represents the payload for a Heartbeat.conf message.
    """
    currentTime: str # ISO 8601 timestamp

@dataclass
class StartTransactionRequest:
    """
    Represents the payload for a StartTransaction.req message.
    """
    connectorId: int
    idTag: str
    timestamp: str
    meterStart: int
    transactionId: Optional[int] = None # Added transactionId
    reservationId: Optional[int] = None

@dataclass
class StartTransactionResponse:
    """
    Represents the payload for a StartTransaction.conf message.
    """
    transactionId: int
    idTagInfo: IdTagInfo

    def __post_init__(self):
        # The JSON library decodes to dicts. We need to convert the nested dict
        # into an IdTagInfo object for type safety and easier access.
        if self.idTagInfo and isinstance(self.idTagInfo, dict):
            self.idTagInfo = IdTagInfo(**self.idTagInfo)

@dataclass
class StopTransactionRequest:
    """
    Represents the payload for a StopTransaction.req message.
    """
    transactionId: int
    timestamp: str
    meterStop: int
    idTag: Optional[str] = None
    reason: Optional[str] = None
    transactionData: Optional[List['MeterValue']] = None

    def __post_init__(self):
        # The JSON library decodes to dicts. We need to convert the nested dicts
        # into MeterValue objects for type safety and easier access.
        if self.transactionData and self.transactionData and isinstance(self.transactionData[0], dict):
            self.transactionData = [MeterValue(**mv) for mv in self.transactionData]

@dataclass
class StopTransactionResponse:
    """
    Represents the payload for a StopTransaction.conf message.
    """
    idTagInfo: Optional[IdTagInfo] = None

    def __post_init__(self):
        if self.idTagInfo and isinstance(self.idTagInfo, dict):
            self.idTagInfo = IdTagInfo(**self.idTagInfo)

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

    def __post_init__(self):
        # The JSON library decodes to dicts. We need to convert the nested dicts
        # into ConfigurationKey objects for type safety and easier access.
        if self.configurationKey and isinstance(self.configurationKey[0], dict):
            self.configurationKey = [ConfigurationKey(**key) for key in self.configurationKey]

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

    def __post_init__(self):
        # The JSON library decodes to dicts. We need to convert the nested dicts
        # into SampledValue objects for type safety and easier access.
        if self.sampledValue and isinstance(self.sampledValue[0], dict):
            self.sampledValue = [SampledValue(**sv) for sv in self.sampledValue]

@dataclass
class MeterValuesRequest:
    """
    Represents the payload for a MeterValues.req message.
    """
    connectorId: int
    meterValue: List[MeterValue]
    transactionId: Optional[int] = None

    def __post_init__(self):
        # The JSON library decodes to dicts. We need to convert the nested dicts
        # into MeterValue objects for type safety and easier access.
        if self.meterValue and isinstance(self.meterValue[0], dict):
            self.meterValue = [MeterValue(**mv) for mv in self.meterValue]

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
class GetCompositeScheduleResponse:
    """
    Represents the payload for a GetCompositeSchedule.conf message.
    """
    status: str  # "Accepted" or "Rejected"
    connectorId: Optional[int] = None
    scheduleStart: Optional[str] = None
    chargingSchedule: Optional['ChargingSchedule'] = None

    def __post_init__(self):
        # The JSON library decodes to dicts. We need to convert the nested dict
        # into a ChargingSchedule object for type safety and easier access.
        if self.chargingSchedule and isinstance(self.chargingSchedule, dict):
            self.chargingSchedule = ChargingSchedule(**self.chargingSchedule)


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

    def __post_init__(self):
        # The JSON library decodes to dicts. We need to convert the nested dicts
        # into ChargingSchedulePeriod objects for type safety and easier access.
        if self.chargingSchedulePeriod and isinstance(self.chargingSchedulePeriod[0], dict):
            self.chargingSchedulePeriod = [ChargingSchedulePeriod(**p) for p in self.chargingSchedulePeriod]


# ---- Payloads for Smart Charging (SetChargingProfile) ----

class ChargingProfilePurposeType:
    """Enum for ChargingProfilePurposeType."""
    ChargePointMaxProfile = "ChargePointMaxProfile"
    TxDefaultProfile = "TxDefaultProfile"
    TxProfile = "TxProfile"

class ChargingProfileKindType:
    """Enum for ChargingProfileKindType."""
    Absolute = "Absolute"
    Recurring = "Recurring"
    Relative = "Relative"

class RecurrencyKindType:
    """Enum for RecurrencyKindType."""
    Daily = "Daily"
    Weekly = "Weekly"

class ChargingRateUnitType:
    """Enum for ChargingRateUnitType."""
    W = "W"
    A = "A"

class ChargingProfileStatusType:
    """Enum for ChargingProfileStatus."""
    Accepted = "Accepted"
    Rejected = "Rejected"
    NotSupported = "NotSupported"

@dataclass
class ChargingProfile:
    """
    A nested object in the SetChargingProfile.req payload.
    """
    chargingProfileId: int
    stackLevel: int
    chargingProfilePurpose: str
    chargingProfileKind: str
    chargingSchedule: 'ChargingSchedule'
    transactionId: Optional[int] = None
    recurrencyKind: Optional[str] = None
    validFrom: Optional[str] = None
    validTo: Optional[str] = None

    def __post_init__(self):
        # The JSON library decodes to dicts. We need to convert the nested dict
        # into a ChargingSchedule object for type safety and easier access.
        if self.chargingSchedule and isinstance(self.chargingSchedule, dict):
            self.chargingSchedule = ChargingSchedule(**self.chargingSchedule)

@dataclass
class SetChargingProfileRequest:
    """
    Represents the payload for a SetChargingProfile.req message.
    """
    connectorId: int
    csChargingProfiles: ChargingProfile

    def __post_init__(self):
        # The JSON library decodes to dicts. We need to convert the nested dict
        # into a ChargingProfile object for type safety and easier access.
        if self.csChargingProfiles and isinstance(self.csChargingProfiles, dict):
            self.csChargingProfiles = ChargingProfile(**self.csChargingProfiles)

@dataclass
class SetChargingProfileResponse:
    """
    Represents the payload for a SetChargingProfile.conf message.
    """
    status: str # "Accepted", "Rejected", "NotSupported"

# ---- Payloads for Smart Charging (ClearChargingProfile) ----

class ClearChargingProfileStatus:
    """Enum for ClearChargingProfileStatus."""
    Accepted = "Accepted"
    Unknown = "Unknown"

@dataclass
class ClearChargingProfileRequest:
    """
    Represents the payload for a ClearChargingProfile.req message.
    """
    id: Optional[int] = None
    connectorId: Optional[int] = None
    chargingProfilePurpose: Optional[str] = None
    stackLevel: Optional[int] = None

@dataclass
class ClearChargingProfileResponse:
    """
    Represents the payload for a ClearChargingProfile.conf message.
    """
    status: str # "Accepted" or "Unknown"

# === NEW: Payloads for Remote Start/Stop Transaction ===

class RemoteStartStopStatus:
    """Enum for RemoteStartStopStatus."""
    Accepted = "Accepted"
    Rejected = "Rejected"

@dataclass
class RemoteStartTransactionRequest:
    """
    Represents the payload for a RemoteStartTransaction.req message.
    """
    idTag: Optional[str] = None  # Made optional for anonymous charging
    connectorId: Optional[int] = None
    chargingProfile: Optional[ChargingProfile] = None

    def __post_init__(self):
        # The JSON library decodes to dicts. We need to convert the nested dict
        # into a ChargingProfile object for type safety and easier access.
        if self.chargingProfile and isinstance(self.chargingProfile, dict):
            self.chargingProfile = ChargingProfile(**self.chargingProfile)

@dataclass
class RemoteStartTransactionResponse:
    """
    Represents the payload for a RemoteStartTransaction.conf message.
    """
    status: str # "Accepted" or "Rejected"

@dataclass
class RemoteStopTransactionRequest:
    """
    Represents the payload for a RemoteStopTransaction.req message.
    """
    transactionId: int

@dataclass
class RemoteStopTransactionResponse:
    """
    Represents the payload for a RemoteStopTransaction.conf message.
    """
    status: str # "Accepted" or "Rejected"

@dataclass
class ResetRequest:
    """
    Represents the payload for a Reset.req message.
    """
    type: str # "Hard" or "Soft"

@dataclass
class ResetResponse:
    """
    Represents the payload for a Reset.conf message.
    """
    status: str # "Accepted" or "Rejected"

class ResetType:
    """Enum for Reset types."""
    Hard = "Hard"
    Soft = "Soft"

# === RFID Authorization List Management ===

class UpdateType:
    """Enum for UpdateType in SendLocalList."""
    Differential = "Differential"
    Full = "Full"

class UpdateStatus:
    """Enum for UpdateStatus in SendLocalList response."""
    Accepted = "Accepted"
    Failed = "Failed"
    NotSupported = "NotSupported"
    VersionMismatch = "VersionMismatch"

@dataclass
class AuthorizationData:
    """
    A nested object in SendLocalList.req payload representing an RFID tag.
    """
    idTag: str
    idTagInfo: Optional[IdTagInfo] = None

    def __post_init__(self):
        if self.idTagInfo and isinstance(self.idTagInfo, dict):
            self.idTagInfo = IdTagInfo(**self.idTagInfo)

@dataclass
class ClearCacheRequest:
    """
    Represents the payload for a ClearCache.req message.
    """
    # ClearCache has no payload

@dataclass
class ClearCacheResponse:
    """
    Represents the payload for a ClearCache.conf message.
    """
    status: str # "Accepted" or "Rejected"

@dataclass
class SendLocalListRequest:
    """
    Represents the payload for a SendLocalList.req message.
    """
    listVersion: int
    updateType: str  # "Differential" or "Full"
    localAuthorizationList: Optional[List[AuthorizationData]] = None

    def __post_init__(self):
        if self.localAuthorizationList and self.localAuthorizationList and isinstance(self.localAuthorizationList[0], dict):
            self.localAuthorizationList = [AuthorizationData(**auth) for auth in self.localAuthorizationList]

@dataclass
class SendLocalListResponse:
    """
    Represents the payload for a SendLocalList.conf message.
    """
    status: str # "Accepted", "Failed", "NotSupported", "VersionMismatch"

@dataclass
class GetLocalListVersionRequest:
    """
    Represents the payload for a GetLocalListVersion.req message.
    """
    # GetLocalListVersion has no payload

@dataclass
class GetLocalListVersionResponse:
    """
    Represents the payload for a GetLocalListVersion.conf message.
    """
    listVersion: int