# EVCC Reboot Behavior - Expected OCPP Message Flow

## Overview
This document describes what EVCC (Electric Vehicle Charge Controller) expects from OCPP wallboxes when EVCC is restarted or rebooted. Understanding this behavior is critical for ensuring proper wallbox simulator functionality.

## Network Topology
```
[Wallbox Simulator] ←→ ws://192.168.0.202:8887 ←→ [EVCC in Home Assistant]
```

## Expected Message Flow When EVCC Restarts

### Phase 1: Connection Loss
When EVCC restarts, the following occurs:

1. **EVCC closes existing WebSocket connections**
   - All connected wallboxes receive connection closure
   - WebSocket status: `ConnectionClosed`

2. **Wallbox behavior (real hardware & simulator)**
   - Detect connection closure
   - Wait a short period (typically 5-10 seconds)
   - Attempt to reconnect to EVCC

### Phase 2: EVCC Startup Sequence
EVCC goes through the following startup phases:

1. **Service Start** (~5-15 seconds)
   - EVCC service starts in Home Assistant
   - Docker container initializes
   - Configuration file loaded from `/addon_configs/49686a9f_evcc/evcc.yaml`

2. **WebSocket Server Ready** (~10-20 seconds total)
   - EVCC opens WebSocket server on port 8887
   - Ready to accept OCPP 1.6 connections
   - Listens for wallbox connections at `ws://192.168.0.202:8887/[StationID]`

### Phase 3: Wallbox Reconnection & Registration

#### 3.1 WebSocket Connection Establishment
```
Wallbox → EVCC: WebSocket CONNECT ws://192.168.0.202:8887/[StationID]
                 Subprotocol: ocpp1.6
EVCC → Wallbox:   WebSocket ACCEPT (101 Switching Protocols)
```

#### 3.2 BootNotification (Required First Message)
**Wallbox → EVCC:**
```json
[2, "message-id", "BootNotification", {
  "chargePointModel": "AcTec SmartCharger",
  "chargePointVendor": "AcTec",
  "chargePointSerialNumber": "Actec",
  "firmwareVersion": "V1.0.0"
}]
```

**EVCC → Wallbox:**
```json
[3, "message-id", {
  "status": "Accepted",
  "currentTime": "2025-11-15T06:17:52Z",
  "interval": 60
}]
```

**Expected behavior:**
- **Status**: Must be `"Accepted"` for wallbox to proceed
- **interval**: Heartbeat interval in seconds (typically 60)
- **currentTime**: EVCC's current UTC time for wallbox clock sync

#### 3.3 StatusNotification (Wallbox Current State)
**Wallbox → EVCC:**
```json
[2, "message-id", "StatusNotification", {
  "connectorId": 1,
  "status": "Available",
  "errorCode": "NoError",
  "timestamp": "2025-11-15T06:17:52.689Z"
}]
```

**EVCC → Wallbox:**
```json
[3, "message-id", {}]
```

**Possible Status Values:**
- `"Available"` - Ready for charging, no vehicle connected
- `"Preparing"` - Vehicle connected, preparing to charge
- `"Charging"` - Active charging session
- `"SuspendedEV"` - Charging suspended by vehicle
- `"SuspendedEVSE"` - Charging suspended by wallbox
- `"Finishing"` - Charging session ending
- `"Reserved"` - Connector reserved
- `"Unavailable"` - Out of service
- `"Faulted"` - Error state

**After Reboot Expectation:**
- Wallbox should report `"Available"` state if no vehicle connected
- If vehicle was charging before reboot, may report `"Preparing"` or `"Charging"`

### Phase 4: EVCC Configuration Commands

After accepting the wallbox, EVCC sends configuration commands:

#### 4.1 ChangeAvailability (Optional)
```json
[2, "msg-id", "ChangeAvailability", {
  "connectorId": 0,
  "type": "Operative"
}]
```

#### 4.2 GetConfiguration
```json
[2, "msg-id", "GetConfiguration", {}]
```

**Expected Response:** Full configuration key list (see configuration section below)

#### 4.3 ChangeConfiguration (Multiple)
EVCC configures wallbox parameters:

```json
[2, "msg-id", "ChangeConfiguration", {
  "key": "MeterValuesSampledData",
  "value": "Power.Active.Import,Energy.Active.Import.Register,Current.Import,Voltage,Current.Offered,Power.Offered,SoC"
}]
```

```json
[2, "msg-id", "ChangeConfiguration", {
  "key": "MeterValueSampleInterval",
  "value": "10"
}]
```

```json
[2, "msg-id", "ChangeConfiguration", {
  "key": "WebSocketPingInterval",
  "value": "30"
}]
```

#### 4.4 TriggerMessage (Request Immediate Data)
```json
[2, "msg-id", "TriggerMessage", {
  "requestedMessage": "BootNotification"
}]
```

```json
[2, "msg-id", "TriggerMessage", {
  "requestedMessage": "MeterValues",
  "connectorId": 1
}]
```

**Purpose:** EVCC requests immediate data to populate its UI

### Phase 5: Normal Operation

#### 5.1 Periodic Heartbeat (Every 60 seconds)
**Wallbox → EVCC:**
```json
[2, "msg-id", "Heartbeat", {}]
```

**EVCC → Wallbox:**
```json
[3, "msg-id", {
  "currentTime": "2025-11-15T06:18:52Z"
}]
```

#### 5.2 Periodic MeterValues (Every 10 seconds)
**Wallbox → EVCC:**
```json
[2, "msg-id", "MeterValues", {
  "connectorId": 1,
  "meterValue": [{
    "timestamp": "2025-11-15T06:17:52.689Z",
    "sampledValue": [
      {"value": "230.0", "measurand": "Voltage", "phase": "L1", "unit": "V"},
      {"value": "230.0", "measurand": "Voltage", "phase": "L2", "unit": "V"},
      {"value": "230.0", "measurand": "Voltage", "phase": "L3", "unit": "V"},
      {"value": "16.5", "measurand": "Current.Import", "phase": "L1", "unit": "A"},
      {"value": "16.3", "measurand": "Current.Import", "phase": "L2", "unit": "A"},
      {"value": "16.7", "measurand": "Current.Import", "phase": "L3", "unit": "A"},
      {"value": "3795", "measurand": "Power.Active.Import", "phase": "L1", "unit": "W"},
      {"value": "3749", "measurand": "Power.Active.Import", "phase": "L2", "unit": "W"},
      {"value": "3841", "measurand": "Power.Active.Import", "phase": "L3", "unit": "W"},
      {"value": "12450", "measurand": "Energy.Active.Import.Register", "unit": "Wh"}
    ]
  }]
}]
```

## Expected Wallbox Configuration Keys

EVCC expects the following configuration keys from `GetConfiguration`:

### Core Configuration (Read-Write)
| Key | Value | Description |
|-----|-------|-------------|
| `AuthorizeRemoteTxRequests` | "true" | Allow EVCC to remotely start transactions |
| `ClockAlignedDataInterval` | "900" | Clock-aligned data reporting interval (seconds) |
| `ConnectionTimeOut` | "90" | WebSocket connection timeout |
| `HeartbeatInterval` | "60" | Heartbeat message interval (seconds) |
| `LocalAuthorizeOffline` | "false" | Authorize when offline |
| `LocalPreAuthorize` | "false" | Pre-authorize without RFID |
| `MeterValueSampleInterval` | "60" | Meter values reporting interval (seconds) |
| `MeterValuesSampledData` | "Energy.Active.Import.Register,Current.Import,Power.Active.Import,SoC,Voltage" | Measurands to report |
| `MeterValuesAlignedData` | "Energy.Active.Import.Register" | Clock-aligned measurands |
| `ResetRetries` | "1" | Number of reset retry attempts |
| `StopTransactionOnEVSideDisconnect` | "true" | Stop when vehicle disconnects |
| `StopTransactionOnInvalidId` | "true" | Stop on invalid RFID |
| `StopTxnAlignedData` | "Energy.Active.Import.Register" | Data sent with StopTransaction |
| `StopTxnSampledData` | "Current.Import" | Sampled data with StopTransaction |
| `TransactionMessageAttempts` | "3" | Retry attempts for transaction messages |
| `TransactionMessageRetryInterval` | "10" | Retry interval (seconds) |
| `UnlockConnectorOnEVSideDisconnect` | "true" | Unlock when vehicle disconnects |
| `WebSocketPingInterval` | "0" | WebSocket ping interval (0=disabled) |
| `LocalAuthListEnabled` | "true" | Enable local authorization list |

### Read-Only Configuration
| Key | Value | Description |
|-----|-------|-------------|
| `GetConfigurationMaxKeys` | "44" | Maximum keys in GetConfiguration |
| `NumberOfConnectors` | "1" | Number of physical connectors |
| `LocalAuthListMaxLength` | "20" | Max entries in auth list |
| `SendLocalListMaxLength` | "20" | Max entries in send list |
| `ChargeProfileMaxStackLevel` | "8" | Max charging profile stack levels |
| `ChargingScheduleAllowedChargingRateUnit` | "Current,Power" | Allowed rate units |
| `ChargingScheduleMaxPeriods` | "5" | Max schedule periods |
| `ConnectorSwitch3to1PhaseSupported` | "false" | 3-phase to 1-phase switching |
| `MaxChargingProfilesInstalled` | "8" | Max charging profiles |
| `SupportedFeatureProfiles` | "Core,FirmwareManagement,LocalAuthListManagement,Reservation,SmartCharging,RemoteTrigger" | OCPP feature profiles |

## State Preservation After Reboot

### What EVCC Expects Wallbox to Preserve:
1. **Energy Counter** - Total energy delivered should NOT reset
   - `Energy.Active.Import.Register` must continue from last value
   - Critical for accurate billing and energy tracking

2. **Configuration Settings** - All ChangeConfiguration values
   - `MeterValueSampleInterval`, `HeartbeatInterval`, etc.
   - Should persist across reboots

### What EVCC Expects Wallbox to Reset:
1. **Connection State** - New WebSocket connection
2. **Active Transaction** - If wallbox rebooted during charging:
   - Transaction ID should be new (if restarted)
   - OR continue existing transaction (advanced)
3. **Connector Status** - Re-evaluate physical state:
   - If no vehicle: `"Available"`
   - If vehicle connected but not charging: `"Preparing"`
   - If vehicle charging: `"Charging"` (may require RemoteStartTransaction)

## Wallbox Simulator Implementation

### Reconnection Logic
```python
while True:  # Retry indefinitely
    try:
        # Connect to EVCC
        websocket = await connect(url, subprotocols=["ocpp1.6"])

        # Reset to Available state but keep energy
        status = "Available"
        transaction_id = None
        charging_limit_watts = 0.0
        # energy counter NOT reset

        # Send BootNotification
        # Send StatusNotification
        # Start periodic tasks (Heartbeat, MeterValues)

        # Receive messages

    except ConnectionClosed:
        # Wait 5 seconds before reconnecting
        await asyncio.sleep(5)
```

## Typical Reboot Timeline

| Time | Event |
|------|-------|
| T+0s | EVCC restarts, closes all connections |
| T+0s | Wallbox detects connection closure |
| T+5s | Wallbox attempts first reconnection (EVCC not ready yet) |
| T+10s | EVCC WebSocket server starts accepting connections |
| T+10s | Wallbox reconnects successfully |
| T+10s | Wallbox sends BootNotification |
| T+10s | EVCC accepts BootNotification |
| T+11s | Wallbox sends StatusNotification |
| T+11s | EVCC sends configuration commands |
| T+12s | EVCC requests TriggerMessage (MeterValues) |
| T+12s | Wallbox sends MeterValues |
| T+15s | Normal operation resumes |

## Common Issues After EVCC Reboot

### 1. Wallbox connects too early
**Symptom:** Connection refused or timeout
**Solution:** Retry logic with 5-second intervals

### 2. Missing BootNotification
**Symptom:** EVCC rejects all messages
**Solution:** BootNotification must be FIRST message after connection

### 3. Energy counter reset to zero
**Symptom:** EVCC shows incorrect energy consumption
**Solution:** Persist energy counter across reboots

### 4. Transaction continues after reboot
**Symptom:** Charging session lost
**Solution:** Reset transaction state, require new RemoteStartTransaction

### 5. Configuration lost
**Symptom:** EVCC re-sends all ChangeConfiguration commands
**Solution:** Expected behavior - EVCC always re-configures after reboot

## Monitoring EVCC Reboot

### Check if EVCC is running:
```bash
# Via SSH to Home Assistant (192.168.0.202)
sshpass -p 'hd*yT1680' ssh root@192.168.0.202 "docker ps | grep evcc"
```

### View EVCC logs:
```bash
sshpass -p 'hd*yT1680' ssh root@192.168.0.202 "docker logs -f addon_49686a9f_evcc"
```

### Restart EVCC:
```bash
sshpass -p 'hd*yT1680' ssh root@192.168.0.202 "ha addons restart 49686a9f_evcc"
```

## Expected OCPP Message Log After Reboot

```
[Actec->evcc] [2, "1000001", "BootNotification", {...}]
[evcc->Actec] [3, "1000001", {"status": "Accepted", "interval": 60, ...}]
[Actec->evcc] [2, "1000002", "StatusNotification", {"status": "Available", ...}]
[evcc->Actec] [3, "1000002", {}]
[evcc->Actec] [2, "...", "ChangeAvailability", {...}]
[evcc->Actec] [2, "...", "GetConfiguration", {}]
[Actec->evcc] [3, "...", {"configurationKey": [...], ...}]
[evcc->Actec] [2, "...", "ChangeConfiguration", {"key": "MeterValuesSampledData", ...}]
[Actec->evcc] [3, "...", {"status": "Accepted"}]
[evcc->Actec] [2, "...", "TriggerMessage", {"requestedMessage": "MeterValues"}]
[Actec->evcc] [2, "...", "MeterValues", {...}]
[evcc->Actec] [3, "...", {}]
[Actec->evcc] [2, "...", "Heartbeat", {}]  // Every 60 seconds
[Actec->evcc] [2, "...", "MeterValues", {...}]  // Every 10 seconds
```

## References

- OCPP 1.6 Specification: https://www.openchargealliance.org/protocols/ocpp-16/
- EVCC Documentation: https://docs.evcc.io/
- Home Assistant Add-on: https://github.com/evcc-io/evcc
