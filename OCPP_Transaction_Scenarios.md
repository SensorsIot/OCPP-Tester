# OCPP 1.6-J Transaction Scenarios

This document maps the OCPP Tester B-series tests to standard OCPP transaction scenarios.

## Table of Contents
- [Standard OCPP Scenarios](#standard-ocpp-scenarios)
- [Test Comparison Matrix](#test-comparison-matrix)
- [Detailed Test Descriptions](#detailed-test-descriptions)
- [Key Insights](#key-insights)

---

## Standard OCPP Scenarios

### 🔌 1. Plug & Charge (Offline Local Start)

Used when the EVSE starts charging immediately after plug-in (e.g., free charging or locally authorized).

**Sequence:**
1. CP → CS: `BootNotification` - On startup; register itself
2. CS → CP: `BootNotification.conf` - Confirms; includes heartbeat interval
3. CP → CS: `StatusNotification` - Connector = Available
4. CP → CS: `StatusNotification` - Connector = Preparing (plug inserted)
5. CP → CS: `StartTransaction` - Start local transaction
6. CS → CP: `StartTransaction.conf` - Returns transactionId
7. CP ↔ CS: `MeterValues` (optional, periodic) - Periodic energy reports
8. CP → CS: `StopTransaction` - End of charging
9. CS → CP: `StopTransaction.conf` - Confirms end

**Characteristic:** Simplest flow — backend mainly logs the transaction.

---

### 🪪 2. Authorize Before Charge (RFID / Card Start)

The most common public charging workflow.

**Sequence:**
1. CP → CS: `BootNotification` - On startup
2. CS → CP: `BootNotification.conf` - Confirms
3. CP → CS: `StatusNotification` - Connector = Available
4. CP → CS: `Authorize(idTag)` - User presents card; CP asks backend
5. CS → CP: `Authorize.conf(status)` - Approve or reject
6. CP → CS: `StartTransaction(idTag)` - Start charging
7. CS → CP: `StartTransaction.conf(transactionId)` - Assign transaction ID
8. CP ↔ CS: `MeterValues` - Periodic
9. CP → CS: `StopTransaction` - When unplugged or manually stopped
10. CS → CP: `StopTransaction.conf` - Confirms end

**Note:** If step 5 returns `Rejected`, no `StartTransaction` follows.

---

### 🛰️ 3. Remote Start / Stop (Smart Charging)

Backend starts or stops a session via network commands, often used by solar-aware controllers or apps.

**Sequence:**
1. CS → CP: `RemoteStartTransaction(idTag, connectorId)` - Backend instructs charge start
2. CP → CS: `Authorize(idTag)` - CP checks authorization (if AuthorizeRemoteTxRequests=true)
3. CS → CP: `Authorize.conf(status=Accepted)` - Confirm
4. CP → CS: `StartTransaction` - Physically start charging
5. CS → CP: `StartTransaction.conf(transactionId)` - Confirm
6. CP ↔ CS: `MeterValues` - Periodic reporting
7. CS → CP: `RemoteStopTransaction(transactionId)` - Backend stops
8. CP → CS: `StopTransaction` - Stop locally
9. CS → CP: `StopTransaction.conf` - Confirm end

**Characteristic:** Most automation-friendly scenario — used by EVCC, SolarManager, etc.

---

## Test Comparison Matrix

| Test | Name | Standard Scenario | Key Configuration | Timing | Authorization Flow |
|------|------|-------------------|-------------------|--------|-------------------|
| **B.1** | RFID Public Charging | ✅ Scenario 2 (exact match) | Default OCPP settings | Tap → Plug → Start | Online via `Authorize` |
| **B.2** | Remote Smart Charging | ✅ Scenario 3 (variation) | `AuthorizeRemoteTxRequests=false` | Plug → Remote cmd → Start | Remote command (no auth check) |
| **B.3** | Offline Local Start | ✅ Scenario 1 (exact match) | `LocalPreAuthorize=true` | Plug → Auto-start | Local (automatic) |

---

## Detailed Test Descriptions

### B.1: RFID Public Charging (Online Authorization)
**Maps to:** Standard Scenario 2 - Authorize Before Charge

**Configuration:**
- Default OCPP settings
- Requires online authorization
- Standard public charging workflow

**Flow:**
```
1. User taps RFID card on wallbox reader
2. Wallbox sends Authorize(idTag) to CS
3. CS responds Authorize.conf (Accepted/Blocked)
4. If Accepted: User plugs in EV
5. Wallbox sends StartTransaction with authorized idTag
6. Charging begins
7. Periodic MeterValues
8. StopTransaction when complete
```

**Use Case:** Public charging stations, fleet management, access control

---

### B.2: Remote Smart Charging
**Maps to:** Standard Scenario 3 - Remote Start/Stop (immediate variant)

**Configuration:**
- `AuthorizeRemoteTxRequests=false` - Skip authorize check for remote commands
- EV **already connected** when command received

**Flow:**
```
1. EV is already plugged in (State B or C)
2. User initiates charging via app/web/QR code
3. CS sends RemoteStartTransaction(idTag, connectorId)
4. Wallbox accepts and starts transaction immediately
5. StartTransaction sent to CS
6. Charging begins
7. Periodic MeterValues
8. RemoteStopTransaction or physical stop
```

**Use Case:**
- QR code payment systems
- Web portal charging
- App-based charging after already plugged in

---

### B.3: Offline Local Start (Plug-and-Charge)
**Maps to:** Standard Scenario 1 - Plug & Charge

**Configuration:**
- `LocalPreAuthorize=true` - Wallbox automatically authorizes on plug-in
- No RFID tap required
- Suitable for private/home charging

**Flow:**
```
1. User plugs in EV (State A → B)
2. Wallbox sends StatusNotification (Preparing)
3. Wallbox automatically starts transaction with default idTag
4. StartTransaction sent to CS
5. Charging begins immediately
6. Periodic MeterValues
7. StopTransaction when unplugged
```

**Use Case:** Private home chargers - "just plug in and charge"

---

## Key Insights

### Scenario Coverage

Your test suite provides **complete coverage** of standard OCPP charging scenarios:

✅ **Scenario 1** - Offline Local Start (B.3)
✅ **Scenario 2** - RFID Public Charging (B.1)
✅ **Scenario 3** - Remote Smart Charging (B.2)

### Real-World Applications

| Test | Typical Deployment |
|------|-------------------|
| **B.1** | Public charging stations, parking lots, shopping centers |
| **B.2** | App-controlled charging, web portals, smart home systems |
| **B.3** | Home chargers, private parking, workplace charging |

---

## Configuration Parameters

Key OCPP configuration parameters used across B tests:

| Parameter | B.2 | B.1 | B.2 | B.1 |
|-----------|-----|-----|-----|-----|
| `LocalPreAuthorize` | false | false | false | **true** |
| `AuthorizeRemoteTxRequests` | **false** | N/A | **false** | N/A |
| `LocalAuthListEnabled` | false | false | false | false |
| `LocalAuthorizeOffline` | false | varies | false | false |

### Configuration Explanations

**LocalPreAuthorize:**
- `true`: Wallbox starts charging immediately on plug-in (B.3)
- `false`: Wallbox waits for authorization (B.2, B.3, B.2)

**AuthorizeRemoteTxRequests:**
- `false`: RemoteStartTransaction commands are trusted without `Authorize` check (B.2, B.2)
- `true`: RemoteStartTransaction requires additional `Authorize` request (Standard Scenario 3)

---

## Message Sequence Diagrams

### B.2: Autonomous Start (Reservation)
```
CS           Wallbox        User
│             │              │
├─RemoteStart─>│              │
│<─Accepted────┤              │
│             │  [Waiting]   │
│             │<─────Plug────┤
│<─StartTx────┤              │
├─Confirm─────>│              │
│             ├──Charging────>│
│<─MeterVals──┤              │
│             │              │
```

### B.1: RFID Tap-to-Charge
```
CS           Wallbox        User
│             │              │
│             │<────Tap──────┤
│<─Authorize──┤              │
├─Accepted───>│              │
│             │<────Plug─────┤
│<─StartTx────┤              │
├─Confirm────>│              │
│             ├──Charging───>│
│<─MeterVals──┤              │
│             │              │
```

### B.2: Remote Start (Immediate)
```
CS           Wallbox        User
│             │              │
│             │<────Plug─────┤
├─RemoteStart─>│              │
│<─Accepted────┤              │
│<─StartTx────┤              │
├─Confirm─────>│              │
│             ├──Charging────>│
│<─MeterVals──┤              │
├─RemoteStop─>│              │
│<─StopTx─────┤              │
```

### B.1: Plug-and-Charge
```
CS           Wallbox        User
│             │              │
│             │<────Plug─────┤
│<─StartTx────┤  (auto)      │
├─Confirm────>│              │
│             ├──Charging───>│
│<─MeterVals──┤              │
│<─StopTx─────┤              │
│             │              │
```

---

## Testing Checklist

When running B-series tests, verify:

- [ ] **B.3** - Charging starts immediately on plug-in (no authorization needed)
- [ ] **B.3** - Authorization request sent before transaction starts
- [ ] **B.2** - RemoteStart works when EV already connected
- [ ] **B.2** - RemoteStart creates reservation that activates on plug-in
- [ ] Configuration parameters are correctly set for each test
- [ ] MeterValues are received periodically during charging
- [ ] StopTransaction includes correct reason codes
- [ ] Transaction IDs are properly managed and unique

---

*Document Version: 1.0*
*Last Updated: 2025-11-12*
*OCPP Version: 1.6-J*
