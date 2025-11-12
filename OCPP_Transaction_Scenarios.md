# OCPP 1.6-J Transaction Scenarios

This document maps the OCPP Tester B-series tests to standard OCPP transaction scenarios.

## Table of Contents
- [Standard OCPP Scenarios](#standard-ocpp-scenarios)
- [Test Comparison Matrix](#test-comparison-matrix)
- [Detailed Test Descriptions](#detailed-test-descriptions)
- [Key Insights](#key-insights)

---

## Standard OCPP Scenarios

### 🔌 1. Plug & Charge (Plug & Charge)

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

### 🪪 2. Authorize Before Plug-in (RFID / Card Start - Online)

The most common public charging workflow. User authorizes first, then plugs in.

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

### 🔐 3. Authorize After Plug-in (Local Authorization Cache)

Offline-capable authorization using local cache. EV plugs in first, then user authorizes.

**Sequence:**
1. CP → CS: `BootNotification` - On startup
2. CS → CP: `BootNotification.conf` - Confirms
3. CP → CS: `StatusNotification` - Connector = Available
4. CP → CS: `StatusNotification` - Connector = Preparing (plug inserted)
5. CP → CS: `Authorize(idTag)` - User presents card; CP checks local cache
6. **Local Cache Hit** - CP validates immediately without waiting
7. CP → CS: `StartTransaction(idTag)` - Start charging immediately
8. CS → CP: `Authorize.conf(status)` - Server acknowledges (parallel/async)
9. CS → CP: `StartTransaction.conf(transactionId)` - Assign transaction ID
10. CP ↔ CS: `MeterValues` - Periodic
11. CP → CS: `StopTransaction` - When unplugged or stopped
12. CS → CP: `StopTransaction.conf` - Confirms end

**Characteristic:** Fast offline authorization - transaction starts within 2 seconds of tap (no network round-trip delay).

---

### 🛰️ 4. Remote Start / Stop (Smart Charging)

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
| **B.1** | RFID Authorization Before Plug-in | ✅ Scenario 2 (exact match) | Default OCPP settings | Tap → Plug → Start | Online via `Authorize` |
| **B.2** | RFID Authorization After Plug-in | ✅ Scenario 3 (exact match) | `LocalAuthListEnabled=true`<br>`LocalAuthorizeOffline=true` | Plug → Tap → Start (< 2s) | Local cache (offline-capable) |
| **B.3** | Remote Smart Charging | ✅ Scenario 4 (exact match) | `AuthorizeRemoteTxRequests=true` | Plug → Remote cmd → Authorize → Start | Remote command (with authorization) |
| **B.4** | Plug & Charge | ✅ Scenario 1 (exact match) | `LocalPreAuthorize=true` | Plug → Auto-start | Local (automatic) |

---

## Detailed Test Descriptions

### B.1: RFID Authorization Before Plug-in (Online Authorization)
**Maps to:** Standard Scenario 2 - Authorize Before Plug-in

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

### B.2: RFID Authorization After Plug-in (Local Cache)
**Maps to:** Standard Scenario 3 - Authorize After Plug-in (Local Authorization Cache)

**Configuration:**
- `LocalAuthListEnabled=true` - Enable local authorization list
- `LocalAuthorizeOffline=true` - Allow offline authorization from cache
- Local cache must contain valid RFID cards

**Flow:**
```
1. User plugs in EV first (State A → B)
2. Wallbox sends StatusNotification (Preparing)
3. User taps RFID card on wallbox reader
4. Wallbox checks local authorization cache (instant validation)
5. Cache HIT: Card found and valid in local list
6. Wallbox immediately starts transaction (< 2 seconds from tap)
7. StartTransaction sent to CS with cached idTag
8. Authorize message sent to CS in parallel (for logging)
9. Charging begins immediately without waiting for network
10. Periodic MeterValues
11. StopTransaction when complete
```

**Key Validation:**
- Transaction start delay < 2 seconds (proves local cache working)
- No waiting for Authorize.conf response before StartTransaction

**Use Case:**
- Parking garages with unreliable network connectivity
- Sites requiring offline authorization capability
- Backup authorization when CSMS unreachable

---

### B.3: Remote Smart Charging
**Maps to:** Standard Scenario 4 - Remote Start/Stop (standard OCPP sequence)

**Configuration:**
- `AuthorizeRemoteTxRequests=true` - Wallbox checks authorization for remote commands
- EV **already connected** when command received

**Flow:**
```
1. EV is already plugged in (State B or C)
2. User initiates charging via app/web/smart charging controller
3. CS sends RemoteStartTransaction(idTag, connectorId)
4. Wallbox sends Authorize(idTag) to CS
5. CS responds Authorize.conf(Accepted)
6. Wallbox starts transaction
7. StartTransaction sent to CS
8. Charging begins
9. Periodic MeterValues
10. RemoteStopTransaction or physical stop
```

**Use Case:**
- Solar-optimized charging (EVCC, SolarManager)
- Dynamic pricing / off-peak charging
- Grid load balancing
- App/web payment-based charging
- QR code payment systems

---

### B.4: Plug & Charge (Plug-and-Charge)
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

✅ **Scenario 1** - Plug & Charge (B.4)
✅ **Scenario 2** - RFID Authorization Before Plug-in (B.1)
✅ **Scenario 3** - RFID Authorization After Plug-in / Local Cache (B.2)
✅ **Scenario 4** - Remote Smart Charging (B.3)

### Real-World Applications

| Test | Typical Deployment |
|------|-------------------|
| **B.1** | Public charging stations, parking lots, shopping centers |
| **B.2** | Parking garages, unreliable networks, offline authorization |
| **B.3** | App-controlled charging, web portals, smart home systems |
| **B.4** | Home chargers, private parking, workplace charging |

---

## Configuration Parameters

Key OCPP configuration parameters used across B tests:

| Parameter | B.1 | B.2 | B.3 | B.4 |
|-----------|-----|-----|-----|-----|
| `LocalPreAuthorize` | false | false | false | **true** |
| `AuthorizeRemoteTxRequests` | N/A | N/A | **true** | N/A |
| `LocalAuthListEnabled` | false | **true** | false | false |
| `LocalAuthorizeOffline` | false | **true** | false | false |

### Configuration Explanations

**LocalPreAuthorize:**
- `true`: Wallbox starts charging immediately on plug-in (B.4)
- `false`: Wallbox waits for authorization (B.1, B.2, B.3)

**AuthorizeRemoteTxRequests:**
- `true`: RemoteStartTransaction triggers `Authorize` check before starting (B.3 - Standard OCPP flow)
- `false`: RemoteStartTransaction starts immediately without `Authorize` check (skips authorization)

**LocalAuthListEnabled:**
- `true`: Enable local authorization cache (B.2)
- `false`: Disable local cache, always use online authorization (B.1, B.3, B.4)

**LocalAuthorizeOffline:**
- `true`: Allow authorization from cache when CSMS unreachable (B.2)
- `false`: Require online authorization (B.1, B.3, B.4)

---

## Message Sequence Diagrams

### B.1: RFID Authorization Before Plug-in
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

### B.2: RFID Authorization After Plug-in (Local Cache)
```
CS           Wallbox        User
│             │              │
│             │<────Plug─────┤
│<─StatusNot──┤ (Preparing)  │
│             │<────Tap──────┤
│             │ [Cache HIT!] │
│<─StartTx────┤ (< 2sec)     │
│<─Authorize──┤ (parallel)   │
├─Accepted───>│              │
├─Confirm────>│              │
│             ├──Charging───>│
│<─MeterVals──┤              │
│             │              │
```
*Note: StartTransaction sent BEFORE waiting for Authorize.conf*

### B.3: Remote Smart Charging (with Authorization)
```
CS           Wallbox        User
│             │              │
│             │<────Plug─────┤
├─RemoteStart─>│              │
│<─Accepted────┤              │
│<─Authorize──┤ (idTag)      │
├─Accepted───>│              │
│<─StartTx────┤              │
├─Confirm─────>│              │
│             ├──Charging────>│
│<─MeterVals──┤              │
├─RemoteStop─>│              │
│<─StopTx─────┤              │
```
*Note: Authorize step included (AuthorizeRemoteTxRequests=true)*

### B.4: Plug & Charge
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
*Note: No authorization needed (LocalPreAuthorize=true)*

---

## Testing Checklist

When running B-series tests, verify:

- [ ] **B.1** - Authorization request sent and accepted before transaction starts
- [ ] **B.1** - Tap → Plug → Start sequence works correctly
- [ ] **B.2** - Transaction starts within 2 seconds of RFID tap (local cache working)
- [ ] **B.2** - Plug → Tap → Start sequence works correctly
- [ ] **B.2** - StartTransaction sent before waiting for Authorize.conf response
- [ ] **B.3** - RemoteStart works when EV already connected
- [ ] **B.3** - RemoteStart accepts command without additional authorization
- [ ] **B.4** - Charging starts immediately on plug-in (no authorization needed)
- [ ] Configuration parameters are correctly set for each test
- [ ] MeterValues are received periodically during charging
- [ ] StopTransaction includes correct reason codes
- [ ] Transaction IDs are properly managed and unique

---

*Document Version: 2.0*
*Last Updated: 2025-11-12*
*OCPP Version: 1.6-J*
*Changes: Added B.2 (Local Cache Authorization), renumbered B.2→B.3 and B.3→B.4*
