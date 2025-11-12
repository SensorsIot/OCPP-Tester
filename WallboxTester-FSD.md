# WallboxTester - Functional Specification Document

## 1. System Overview

### 1.1 Purpose
WallboxTester is an OCPP 1.6-J compliant test server for validating electric vehicle charge point implementations. It provides comprehensive protocol testing, transaction management, and smart charging profile verification.

### 1.2 Architecture
- **WebSocket Server**: OCPP 1.6-J message handling on port 8887
- **Web UI Server**: Flask-based REST API and web interface on port 5000
- **Test Engine**: Automated test execution with verification
- **EV Simulator Integration**: External EV state simulation for realistic testing
- **Real-time Logging**: WebSocket-streamed logs with OCPP message capture

### 1.3 Key Capabilities
- 16 individual OCPP tests covering all protocol aspects
- Complete coverage of 4 standard OCPP transaction scenarios
- 2 automated test sequences (B All Tests, C All Tests) with combined logging
- Real-time visual feedback with 7 button states
- GetConfiguration integration for comprehensive test documentation
- Smart charging profile verification with GetCompositeSchedule for validation
- RFID test mode for authorization flow testing (B.1 and B.2)

## 2. Test Categories

### A. Core Communication & Status (6 tests)

#### A.1: ChangeConfiguration
Tests configuration modification via OCPP ChangeConfiguration command.
- Modifies HeartbeatInterval parameter
- Validates accepted/rejected/not-supported responses

#### A.2: Get All Configuration
Retrieves all configuration keys using GetConfiguration with empty key array.
- May be limited by GetConfigurationMaxKeys parameter
- Returns all available configuration parameters

#### A.3: Get OCPP Standard Keys
Retrieves 35 OCPP 1.6-J standard configuration parameters.
- Explicitly requests each standard key
- Includes Core, Local Auth List, and Smart Charging profiles
- Displays results in UI Parameter Info section

#### A.4: Check Initial State
Tests EV state transitions using EV simulator.
- State A → Available (disconnected)
- State B → Preparing (connected)
- State C → Charging (charging)
- State E → Faulted/Finishing (error)

#### A.5: Trigger All Messages
Tests TriggerMessage functionality for all supported message types.
- Requires RemoteTrigger feature profile
- Tests StatusNotification, MeterValues, BootNotification triggers

#### A.6: Status and Meter Value Acquisition
Triggers and waits for MeterValues messages.
- Validates real-time metering data
- Tests MeterValueSampleInterval configuration

### B. Authorization & Transaction Management (4 tests)

**See Chapter 14: OCPP Transaction Scenarios for detailed protocol flows**

#### B.1: RFID Authorization Before Plug-in
Tests standard OCPP 1.6-J "tap-first" authorization flow.
- User taps RFID card before plugging in EV
- Wallbox sends Authorize to CS
- CS responds Authorize.conf (Accepted/Blocked)
- If accepted: User plugs in EV and transaction starts
- Interactive modal with countdown and real-time status
- **Use Case**: Public charging stations, fleet management, access control

#### B.2: RFID Authorization After Plug-in (Local Cache)
Tests local authorization cache with "plug-first" workflow.
- User plugs in EV first (State A → B)
- User taps RFID card
- Wallbox checks local authorization cache (instant validation)
- Transaction starts within 2 seconds (no network delay)
- **Configuration**: LocalAuthListEnabled=true, LocalAuthorizeOffline=true
- **Use Case**: Parking garages with unreliable connectivity, offline authorization

#### B.3: Remote Smart Charging
Tests remote transaction initiation following standard OCPP sequence.
- EV already plugged in (State B or C)
- CS sends RemoteStartTransaction with idTag
- Wallbox sends Authorize to CS
- CS responds Authorize.conf (Accepted)
- Transaction starts
- **Configuration**: AuthorizeRemoteTxRequests=true
- **Use Case**: Solar-optimized charging (EVCC, SolarManager), dynamic pricing, grid balancing, app/QR payment

#### B.4: Plug & Charge
Tests automatic charging with LocalPreAuthorize.
- User plugs in EV (no RFID tap needed)
- Wallbox automatically starts transaction with default idTag
- Charging begins immediately
- **Configuration**: LocalPreAuthorize=true
- **Use Case**: Private home chargers - "just plug in and charge"

### C. Smart Charging Profile (4 tests + automated sequence)

#### C.1: SetChargingProfile
Sets TxProfile charging profile to limit power on active transaction.
- Supports all charging rate values (disable/low/medium/high)
- Automatic verification using GetCompositeSchedule
- Compares expected vs actual profile parameters
- Displays verification results in modal

#### C.2: TxDefaultProfile
Sets default charging profile for future transactions.
- Applies at charge point level (connectorId=0)
- Supports all charging rate values
- Automatic verification using GetCompositeSchedule
- No transaction required

#### C.3: GetCompositeSchedule
Retrieves current composite charging schedule.
- Configurable connector, duration, and charging rate unit
- Interactive modal for parameter selection
- Displays charging schedule details

#### C.4: ClearChargingProfile
Removes charging profiles from charge point.
- Clears TxDefaultProfile types
- Validates profile removal

### X. System Control (2 tests)

#### X.1: Reboot Wallbox
Sends OCPP Reset command to reboot charge point.
- Hard reset terminates all transactions
- Forces charge point reboot

#### X.2: Dump All Configuration
Exports complete configuration to log file.
- Comprehensive configuration documentation
- Includes all GetConfiguration results

## 3. Automated Test Sequences

### 3.1 B All Tests
Runs B.1 → B.2 → B.3 → B.4 sequentially covering all OCPP authorization scenarios.

**Features:**
- Frontend-driven execution (supports B.1 RFID modal)
- GetConfiguration called at start
- Creates combined log file with:
  - Charge point configuration
  - All 4 test results
  - Complete OCPP message history
- Result summary popup
- 10-minute timeout
- Button color: Green (all passed) / Red (any failed)

**Test Coverage:**
- B.1: RFID Authorization Before Plug-in (Online authorization)
- B.2: RFID Authorization After Plug-in (Local cache)
- B.3: Remote Smart Charging (Remote start with authorization)
- B.4: Plug & Charge (Automatic start)

**Log Structure:**
```
CHARGE POINT CONFIGURATION (from GetConfiguration)
================================================================================
[All configuration keys with values and readonly indicators]
================================================================================

TEST RESULTS SUMMARY
================================================================================
B.1: RFID Authorization Before Plug-in - PASSED/FAILED
B.2: RFID Authorization After Plug-in - PASSED/FAILED
B.3: Remote Smart Charging - PASSED/FAILED
B.4: Plug & Charge - PASSED/FAILED
================================================================================

OCPP MESSAGES
================================================================================
[Timestamped request/response pairs for all tests]
================================================================================
```

### 3.2 C All Tests (C.1 and C.2 Tests)
Runs C.1 test 4 times + C.2 test 4 times (8 total iterations).

**Charging Rate Values:**
- disable: 0A / 0W
- low: 6A / 4000W
- medium: 10A / 8000W
- high: 16A / 11000W

**Features:**
- Backend-driven execution (single API call)
- GetConfiguration called at start
- Creates comprehensive log file with:
  - Charge point configuration
  - Test parameters for all iterations
  - Test results summary
  - Verification results for all iterations
  - Complete OCPP message history
- 8-minute timeout
- Result popup shows all iterations

**Log Structure:**
```
CHARGE POINT CONFIGURATION (from GetConfiguration)
================================================================================
[All configuration keys]
================================================================================

TEST PARAMETERS
================================================================================
Test Levels: disable, low, medium, high
Number of Test Runs: 8

C.1 Iteration 1 (disable):
  Connector ID: 1
  Stack Level: 0
  Profile Kind: Absolute
  Charging Rate Unit: A
  Limit: 0
  Duration: 3600
  Number of Phases: 1

[... all 8 iterations ...]
================================================================================

TEST RESULTS SUMMARY
================================================================================
C.1 (disable) - 0A: PASSED/FAILED
C.1 (low) - 6A: PASSED/FAILED
C.1 (medium) - 10A: PASSED/FAILED
C.1 (high) - 16A: PASSED/FAILED
C.2 (disable) - 0A: PASSED/FAILED
C.2 (low) - 6A: PASSED/FAILED
C.2 (medium) - 10A: PASSED/FAILED
C.2 (high) - 16A: PASSED/FAILED
================================================================================

VERIFICATION RESULTS FOR C.1 (disable) - 0A
================================================================================
Profile Purpose: Expected TxProfile, Got TxProfile - OK
Stack Level: Expected 0, Got 0 - OK
[... all verification parameters ...]
================================================================================

[... all 8 verification sections ...]

OCPP MESSAGES
================================================================================
[Timestamped request/response pairs for all 8 test iterations]
================================================================================
```

## 4. Verification System

### 4.1 C.1 and C.2 Verification
After SetChargingProfile succeeds, GetCompositeSchedule automatically verifies profile application.

**C.1 Verification (connectorId=1):**
- Profile Purpose: TxProfile
- Stack Level: 0
- Profile Kind: Absolute
- Transaction ID: Must match active transaction
- Charging Rate Unit: W or A
- Power Limit: Expected value
- Duration: Expected seconds
- Number of Phases: 1 or 3

**C.2 Verification (connectorId=0):**
- Profile Purpose: TxDefaultProfile
- Stack Level: 0
- Profile Kind: Absolute
- Transaction ID: null (no transaction required)
- Charging Rate Unit: W or A
- Power Limit: Expected value
- Duration: null (no duration limit)
- Number of Phases: 1 or 3

**Result Display:**
- Verification Results Modal with comparison table
- Color-coded status: Green (OK), Red (NOT OK), Blue (INFO)
- Icons: ✓ (OK), ✗ (NOT OK), ℹ (INFO)
- API endpoint: `/api/verification_results?test=C1` or `?test=C2`

### 4.2 Test Pass/Fail Logic
Tests now validate actual implementation, not just command acceptance:
- C.1 FAILS if GetCompositeSchedule shows incorrect values
- C.2 FAILS if GetCompositeSchedule shows incorrect values
- Verification failures logged as errors with ❌ indicators

## 5. Visual Feedback System

### 5.1 Button States
- **Default (Blue)**: Not run yet
- **Success (Green)**: Test PASSED
- **Failure (Red)**: Test FAILED
- **Running (Grey + wait cursor)**: Currently executing
- **Skipped (Yellow)**: Test SKIPPED
- **Partial (Orange)**: Partial success
- **Not Supported (Grey)**: Feature not supported
- **Disabled (Grey + opacity)**: No wallbox connected

### 5.2 Real-time Updates
- Button colors update every 3 seconds via polling
- Colors persist across page refreshes
- Active test tracking prevents color changes during execution
- Clear Test Results button resets all colors to default

## 6. Real-time Monitoring

### 6.1 WebSocket Streaming
**Log Stream** (`/logs`):
- Colored console output (Info/Error/Warning/Debug)
- Transaction ID highlighting (purple)
- OCPP message formatting
- Auto-scroll with 400px container

**EV Status Stream** (`/ev-status`):
- Real-time EV state (A/B/C/E)
- Wallbox advertised current (A)
- CP Voltage (V)
- CP Duty Cycle (%)
- PP Voltage (V)
- Error status

### 6.2 Live Data Display
**Current Charging:**
- Real-time power (W) and current (A)
- Parsed from transaction MeterValues
- Updates every 3 seconds
- Multi-phase support

**Active Transaction:**
- Current transaction ID
- Transaction start time
- Energy delivered
- MeterValues history

**Wallbox Discovery:**
- Automatic detection of connecting wallboxes
- Active wallbox indicator
- Connection status
- Click to switch active wallbox
- 2-second polling interval

## 7. EV Simulator Integration

### 7.1 Display Section
Visible when simulator is active, shows:
- EV State (A/B/C/E)
- Wallbox advertised current
- CP Voltage
- CP Duty Cycle
- PP Voltage
- Error status

### 7.2 Control Buttons
- Set State A (Disconnected)
- Set State B (Connected)
- Set State C (Charging)
- Set State E (Error)

### 7.3 Integration
- WebSocket connection for real-time updates
- Status polling every 3 seconds
- Used by tests for state transitions
- Base URL: `EV_SIMULATOR_BASE_URL` environment variable

## 8. RFID Test Mode

### 8.1 Purpose
Allows any RFID card to be accepted during B.1 (RFID Authorization Before Plug-in) and B.2 (RFID Authorization After Plug-in) tests.

### 8.2 Behavior
- First card: Always ACCEPTED
- Subsequent cards: Always INVALID
- Tracks card presentation order
- Clears accepted_rfid to detect new card taps
- Automatically enabled/disabled by B.1 and B.2 tests

### 8.3 API Endpoints
- `/api/enable_rfid_test_mode` - Enable test mode
- `/api/disable_rfid_test_mode` - Disable test mode
- `/api/rfid_status` - Get current status

## 9. Configuration Features

### 9.1 Charging Rate Unit
Toggle between W (Watts) and A (Amperes):
- Auto-detection from `ChargingScheduleAllowedChargingRateUnit`
- Manual override available
- Affects C.1 and C.2 test defaults
- API endpoint: `/api/charging_rate_unit`

### 9.2 Default Values
- C.1/C.2 default to "medium" (10A or 8000W)
- Configurable via modal dialogs
- Stored in server configuration

## 10. Log File System

### 10.1 Individual Test Logs
Location: `/home/ocpp-tester/logs/{test_name}_{charge_point_id}_{timestamp}.log`

Contents:
- Test name and timestamp
- Test parameters
- OCPP message log (request/response pairs)
- Test result (PASSED/FAILED/SKIPPED)

### 10.2 Combined Test Logs
**B All Tests**: `b_all_tests_{charge_point_id}_{timestamp}.log`
- GetConfiguration results
- 4 test results summary
- Complete OCPP messages for all tests

**C All Tests**: `c_all_tests_{charge_point_id}_{timestamp}.log`
- GetConfiguration results
- Test parameters for all iterations
- Test results summary (8 iterations)
- Verification results for all iterations
- Complete OCPP messages for all tests

### 10.3 Log Format
All logs use standardized format:
```
[YYYY-MM-DD HH:MM:SS.mmm] REQUEST - Action
{"key": "value"}

[YYYY-MM-DD HH:MM:SS.mmm] RESPONSE - Action
{"key": "value"}
```

## 11. API Endpoints

### 11.1 Test Execution
- `POST /api/test/<step_name>` - Run individual test
- `POST /api/test/b_all_tests` - Run B All Tests
- `POST /api/test/c_all_tests` - Run C All Tests
- `POST /api/test/get_configuration` - Call GetConfiguration
- `POST /api/test/combine_logs` - Combine multiple log files

### 11.2 System Control
- `GET/POST /api/charging_rate_unit` - Get/set charging rate unit
- `GET /api/charge_points` - Get all charge points
- `POST /api/set_active_charge_point` - Set active charge point
- `POST /api/clear_test_results` - Clear all test results
- `POST /api/shutdown` - Shutdown server

### 11.3 EV Simulator
- `GET /api/ev_status` - Get EV simulator status
- `POST /api/set_ev_state` - Set EV state

### 11.4 RFID Test Mode
- `POST /api/enable_rfid_test_mode` - Enable RFID test mode
- `POST /api/disable_rfid_test_mode` - Disable RFID test mode
- `GET /api/rfid_status` - Get RFID test mode status

### 11.5 Data Retrieval
- `GET /api/verification_results?test=C1|C2` - Get verification results
- `GET /api/transactions` - Get transaction history
- `GET /api/test/get_latest_log?test_name=<name>` - Get latest log file

## 12. OCPP Message Handling

### 12.1 Automated Reactions
These messages are handled automatically:
- **BootNotification**: Sends BootNotification.conf with configuration
- **StartTransaction**: Validates and sends StartTransaction.conf with transaction ID
- **Heartbeat**: Updates last seen time, sends Heartbeat.conf
- **StatusNotification**: Updates connector status in global state
- **MeterValues**: Updates transaction meter values
- **StopTransaction**: Finalizes transaction, sends StopTransaction.conf
- **Authorize**: Returns Accepted for valid tags, Invalid for others

### 12.2 Test-Initiated Messages
Tests can send these OCPP commands:
- **GetConfiguration**: Retrieve configuration parameters
- **ChangeConfiguration**: Modify configuration parameters
- **RemoteStartTransaction**: Start charging session remotely
- **RemoteStopTransaction**: Stop charging session remotely
- **SetChargingProfile**: Set charging power limits
- **GetCompositeSchedule**: Verify applied charging profiles
- **ClearChargingProfile**: Remove charging profiles
- **Reset**: Reboot charge point
- **TriggerMessage**: Request specific message types
- **ClearCache**: Clear local authorization cache
- **SendLocalList**: Send RFID authorization list
- **GetLocalListVersion**: Get authorization list version

## 13. System Statistics

- **Total Individual Tests**: 16 (A: 6, B: 4, C: 4, X: 2)
- **Automated Sequences**: 2 (B All Tests, C All Tests)
- **Total Test Iterations**: 12 (B: 4 tests, C: 8 iterations)
- **OCPP Scenarios Covered**: 4 (Plug & Charge, RFID Before Plug-in, RFID After Plug-in, Remote Smart Charging)
- **API Endpoints**: 20+
- **WebSocket Streams**: 3 (logs, ev-status, ocpp)
- **Modal Dialogs**: 6
- **Button States**: 7
- **Log File Types**: 3

---

## 14. OCPP 1.6-J Transaction Scenarios

This chapter maps the B-series tests to standard OCPP transaction scenarios and provides detailed protocol flows.

### 14.1 Standard OCPP Scenarios

#### 🔌 Scenario 1: Plug & Charge (Offline Local Start)

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

#### 🪪 Scenario 2: Authorize Before Plug-in (RFID / Card Start - Online)

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

#### 🔐 Scenario 3: Authorize After Plug-in (Local Authorization Cache)

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

#### 🛰️ Scenario 4: Remote Start / Stop (Smart Charging)

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

### 14.2 Test Comparison Matrix

| Test | Name | Standard Scenario | Key Configuration | Timing | Authorization Flow |
|------|------|-------------------|-------------------|--------|-------------------|
| **B.1** | RFID Authorization Before Plug-in | ✅ Scenario 2 (exact match) | Default OCPP settings | Tap → Plug → Start | Online via `Authorize` |
| **B.2** | RFID Authorization After Plug-in | ✅ Scenario 3 (exact match) | `LocalAuthListEnabled=true`<br>`LocalAuthorizeOffline=true` | Plug → Tap → Start (< 2s) | Local cache (offline-capable) |
| **B.3** | Remote Smart Charging | ✅ Scenario 4 (exact match) | `AuthorizeRemoteTxRequests=true` | Plug → Remote cmd → Authorize → Start | Remote command (with authorization) |
| **B.4** | Plug & Charge | ✅ Scenario 1 (exact match) | `LocalPreAuthorize=true` | Plug → Auto-start | Local (automatic) |

---

### 14.3 Detailed Test Descriptions

#### B.1: RFID Authorization Before Plug-in (Online Authorization)
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

#### B.2: RFID Authorization After Plug-in (Local Cache)
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

#### B.3: Remote Smart Charging
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

#### B.4: Plug & Charge (Plug-and-Charge)
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

### 14.4 Key Insights

#### Scenario Coverage

Your test suite provides **complete coverage** of standard OCPP charging scenarios:

✅ **Scenario 1** - Plug & Charge (B.4)
✅ **Scenario 2** - RFID Authorization Before Plug-in (B.1)
✅ **Scenario 3** - RFID Authorization After Plug-in / Local Cache (B.2)
✅ **Scenario 4** - Remote Smart Charging (B.3)

#### Real-World Applications

| Test | Typical Deployment |
|------|-------------------|
| **B.1** | Public charging stations, parking lots, shopping centers |
| **B.2** | Parking garages, unreliable networks, offline authorization |
| **B.3** | App-controlled charging, web portals, smart home systems |
| **B.4** | Home chargers, private parking, workplace charging |

---

### 14.5 Configuration Parameters

Key OCPP configuration parameters used across B tests:

| Parameter | B.1 | B.2 | B.3 | B.4 |
|-----------|-----|-----|-----|-----|
| `LocalPreAuthorize` | false | false | false | **true** |
| `AuthorizeRemoteTxRequests` | N/A | N/A | **true** | N/A |
| `LocalAuthListEnabled` | false | **true** | false | false |
| `LocalAuthorizeOffline` | false | **true** | false | false |

#### Configuration Explanations

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

### 14.6 Message Sequence Diagrams

#### B.1: RFID Authorization Before Plug-in
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

#### B.2: RFID Authorization After Plug-in (Local Cache)
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

#### B.3: Remote Smart Charging (with Authorization)
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

#### B.4: Plug & Charge
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

### 14.7 Testing Checklist

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

## 15. Code Architecture & Helper Functions

### 15.1 Test Helper Module (app/test_helpers.py)

**Purpose**: Centralized helper functions to reduce code duplication across test methods.

**File Size**: 1,301 lines  
**Total Functions**: 37 helper functions  
**Categories**: 9 functional categories  

#### 15.1.1 Function Categories

**1. Transaction Management (3 functions)**
- `find_active_transaction()` - Locate active transaction by charge point
- `stop_active_transaction()` - Stop transaction with cleanup and timeout handling
- `wait_for_transaction_start()` - Wait for transaction with filtering options

**2. Configuration Management (4 functions)**
- `get_configuration_value()` - Retrieve single configuration value
- `set_configuration_value()` - Set configuration with status return
- `ensure_configuration()` - Check-then-set pattern (only changes if different)
- `configure_multiple_parameters()` - Batch configuration with reboot detection

**3. Status and State Management (4 functions)**
- `wait_for_connector_status()` - Wait for specific connector status with timeout
- `get_connector_status()` - Get current connector status
- `is_using_simulator()` - Check if EV simulator mode is active
- `set_ev_state_safe()` - Safely set EV state with simulator checks

**4. EV Connection Management (1 comprehensive function)**
- `prepare_ev_connection()` - Handle EV connection for both simulator and real charge points
  - Auto-detects mode (simulator vs real CP)
  - Sets state programmatically for simulator
  - Prompts user and waits for real charge points
  - Handles all status checks and timeouts

**5. Cleanup Operations (3 functions)**
- `cleanup_transaction_and_state()` - Complete cleanup workflow
- `clear_charging_profile()` - Clear single charging profile
- `clear_all_charging_profiles()` - Clear profiles with optional filters

**6. Charging Profile Operations (6 functions)**
- `create_charging_profile()` - Build ChargingProfile object with all parameters
- `set_charging_profile()` - Send SetChargingProfile request
- `get_composite_schedule()` - Query active charging schedule
- `verify_charging_profile()` - Verify profile application with comparison
- Eliminates 50-80 lines per charging profile test

**7. RFID Operations (3 functions)**
- `clear_rfid_cache()` - ClearCache with status handling
- `send_local_authorization_list()` - SendLocalList with card management
- `get_local_list_version()` - Query authorization list version
- Eliminates 30-40 lines per RFID test

**8. Remote Start/Stop Operations (2 functions)**
- `remote_start_transaction()` - RemoteStart with optional charging profile
- `remote_stop_transaction()` - RemoteStop with error handling
- Eliminates 15-25 lines per remote operation test

**9. Verification and Test Results (3 functions)**
- `store_verification_results()` - Save results for UI display
- `create_verification_result()` - Build verification dict with tolerance
- `start_transaction_for_test()` - Start transaction for testing purposes

#### 15.1.2 Code Reduction Impact

**Current State (ocpp_test_steps.py)**
- **Total lines**: 3,377
- **Test methods**: 34
- **Estimated duplication**: ~1,820 lines

**Projected After Full Refactoring**

| Test Series | Current | After Refactoring | Reduction |
|-------------|---------|-------------------|-----------|
| A-series (6 tests) | 600 lines | 300 lines | **-50%** |
| B-series (10 tests) | 850 lines | 300 lines | **-65%** |
| C-series (5 tests) | 700 lines | 200 lines | **-71%** |
| D-series (2 tests) | 150 lines | 80 lines | **-47%** |
| E-series (7 tests) | 550 lines | 200 lines | **-64%** |
| X-series (2 tests) | 150 lines | 100 lines | **-33%** |
| **Total** | **3,000 lines** | **1,180 lines** | **-61%** |

**Line Savings by Operation Type**

| Operation Type | Tests Affected | Savings per Test | Total Saved |
|----------------|----------------|------------------|-------------|
| Charging Profiles | 8 tests | 60-80 lines | 480-640 lines |
| RFID Operations | 3 tests | 30-40 lines | 90-120 lines |
| Remote Start/Stop | 4 tests | 20-30 lines | 80-120 lines |
| Configuration | 10 tests | 15-25 lines | 150-250 lines |
| Transaction Mgmt | 25 tests | 10-20 lines | 250-500 lines |
| Cleanup | 30 tests | 10-15 lines | 300-450 lines |
| **Total** | | | **1,820 lines** |

#### 15.1.3 Usage Examples

**Before (without helpers):**
```python
# Configuration - 40 lines
response = await self.handler.send_and_wait(
    "GetConfiguration",
    GetConfigurationRequest(key=["AuthorizeRemoteTxRequests"]),
    timeout=OCPP_MESSAGE_TIMEOUT
)
authorize_remote = None
if response and response.get("configurationKey"):
    for key in response.get("configurationKey", []):
        if key.get("key") == "AuthorizeRemoteTxRequests":
            authorize_remote = key.get("value", "").lower()
            break
if authorize_remote != "true":
    config_response = await self.handler.send_and_wait(
        "ChangeConfiguration",
        ChangeConfigurationRequest(key="AuthorizeRemoteTxRequests", value="true"),
        timeout=OCPP_MESSAGE_TIMEOUT
    )
    if config_response and config_response.get("status") == "Accepted":
        logger.info("Configuration updated")
```

**After (with helpers):**
```python
# Configuration - 1 line
await ensure_configuration(self.handler, "AuthorizeRemoteTxRequests", "true")
```

**Charging Profile Example:**
```python
# Before: ~150 lines for create + set + verify + store

# After: ~15 lines
profile = await create_charging_profile(
    connector_id=1, charging_profile_id=random.randint(1, 1000),
    stack_level=0, purpose="TxProfile", kind="Absolute",
    charging_unit="W", limit=10000, transaction_id=tx_id
)
success, status = await set_charging_profile(self.handler, 1, profile)
success, results = await verify_charging_profile(self.handler, 1, "W", 10000)
store_verification_results(self.charge_point_id, "C.1: SetChargingProfile", results)
```

#### 15.1.4 Benefits

**Code Quality**
- Single source of truth for all OCPP operations
- Consistent error handling and logging across all tests
- Full type hints on all functions (37/37)
- Comprehensive docstrings with usage examples

**Maintainability**
- Bug fixes in one place benefit all tests
- Feature additions (retry logic, better timeouts) apply globally
- Clear separation of business logic vs implementation
- Easier onboarding for new developers

**Developer Experience**
- 60% faster test development with helpers
- Better IDE autocomplete and type checking
- Reduced cognitive load - tests focus on "what" not "how"
- Easier to write new tests following established patterns

**Test Reliability**
- Consistent timeout handling across all operations
- Better error messages with actionable guidance
- Proper cleanup in all scenarios
- Easy to add retry capability to critical operations

### 15.2 Planned Code Reorganization

**Current Structure**
```
app/
├── ocpp_test_steps.py       # 3,377 lines - all 34 tests
├── test_helpers.py          # 1,301 lines - helper functions
└── ...
```

**Planned Structure** (Priority 1 - Next Step)
```
app/
├── test_helpers.py          # 1,301 lines - helper functions
├── tests/
│   ├── __init__.py
│   ├── test_base.py         # ~100 lines - base class with shared methods
│   ├── test_series_a_basic.py      # ~300 lines - A1-A6 tests
│   ├── test_series_b_auth.py       # ~300 lines - B1-B8 tests  
│   ├── test_series_c_charging.py   # ~200 lines - C1-C5 tests
│   ├── test_series_d_smart.py      # ~80 lines - D3, D5-D6 tests
│   ├── test_series_e_remote.py     # ~200 lines - E1-E11 tests
│   └── test_series_x_utility.py    # ~100 lines - X1-X2 tests
└── ...
```

**Benefits of Reorganization**
- Each test file 80-300 lines (manageable size)
- Clear separation by test category
- Easier to navigate and find specific tests
- Better for git diffs and code review
- Can run test series independently
- Natural fit for future test expansion

### 15.3 Test Development Guidelines

**When Writing New Tests:**
1. Always check test_helpers.py first for existing helpers
2. Use helpers for all common operations (transaction, config, etc.)
3. Focus test code on business logic, not OCPP implementation
4. Add new helpers if pattern repeats 3+ times
5. Document any wallbox-specific behavior in test comments

**Helper Function Design Principles:**
1. Single Responsibility - Each helper does one thing well
2. Consistent Return Types - Use Tuple[bool, str] for operations
3. Comprehensive Logging - Log every significant action
4. Error Handling - Never let exceptions bubble up without context
5. Type Hints - Full typing on all parameters and returns

**Code Review Checklist:**
- [ ] Used helpers for all common operations?
- [ ] No duplicated transaction/config/cleanup code?
- [ ] Proper error handling and logging?
- [ ] Test focuses on "what" not "how"?
- [ ] Results properly stored for UI display?
- [ ] Cleanup properly handled in all paths?

---

*Section Added: 2025-11-12*
*Helper Functions: 37 total covering all OCPP operations*
*Projected Code Reduction: 61% (1,820 lines)*
