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
- 20+ individual OCPP tests covering all protocol aspects
- 2 automated test sequences with combined logging
- Real-time visual feedback with 7 button states
- GetConfiguration integration for comprehensive test documentation
- Smart charging profile verification with GetCompositeSchedule
- RFID test mode for authorization flow testing

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

### B. Authorization & Transaction Management (8 tests)

#### B.1: Reset Transaction Management
Resets transaction state and checks for offline authorization issues.
- Validates clean transaction environment
- Warns if offline authorization detected

#### B.2: Autonomous Start
Tests autonomous transaction initiation without remote commands.
- EV connects and starts charging without RemoteStartTransaction
- Validates autonomous charging capability

#### B.3: RFID Tap-to-Charge
Tests standard OCPP 1.6-J authorization flow.
- User taps RFID card → Authorization → EV plugs in → Transaction starts
- Interactive modal with countdown and real-time status
- RFID test mode: first card accepted, subsequent cards invalid

#### B.4: Anonymous Remote Start
Tests RemoteStartTransaction without ID tag.
- Free charging or external payment scenarios
- No user identification required
- Informational modal during execution

#### B.5: Plug-and-Charge
Tests automated charging with pre-authorized ID tag.
- Transaction starts automatically when EV connects
- No manual authorization required

#### B.6: Clear RFID Cache
Clears authorization cache using ClearCache command.
- Removes locally stored RFID cards
- Returns "NotSupported" if feature unavailable

#### B.7: Send RFID List
Sends local authorization list using SendLocalList command.
- Adds TEST_CARD_001, TEST_CARD_002, TEST_CARD_003
- Returns "NotSupported" if feature unavailable

#### B.8: Get RFID List Version
Retrieves local authorization list version.
- Uses GetLocalListVersion command
- Returns -1 if feature unavailable

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
Runs B.2 → B.3 → B.4 → B.5 sequentially.

**Features:**
- Frontend-driven execution (supports B.3 modal)
- GetConfiguration called at start
- Creates combined log file with:
  - Charge point configuration
  - All 4 test results
  - Complete OCPP message history
- Result summary popup
- 10-minute timeout
- Button color: Green (all passed) / Red (any failed)

**Log Structure:**
```
CHARGE POINT CONFIGURATION (from GetConfiguration)
================================================================================
[All configuration keys with values and readonly indicators]
================================================================================

TEST RESULTS SUMMARY
================================================================================
B.2: Autonomous Start - PASSED/FAILED
B.3: Tap to Charge - PASSED/FAILED
B.4: Anonymous Remote Start - PASSED/FAILED
B.5: Plug and Charge - PASSED/FAILED
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
Allows any RFID card to be accepted during B.3 Tap-to-Charge test.

### 8.2 Behavior
- First card: Always ACCEPTED
- Subsequent cards: Always INVALID
- Tracks card presentation order
- Clears accepted_rfid to detect new card taps
- Automatically enabled/disabled by B.3 test

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
Location: `/home/ocpp/logs/{test_name}_{charge_point_id}_{timestamp}.log`

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

- **Total Individual Tests**: 20 (A: 6, B: 8, C: 4, X: 2)
- **Automated Sequences**: 2 (B All Tests, C All Tests)
- **Total Test Iterations**: 12 (B: 4 tests, C: 8 iterations)
- **API Endpoints**: 20+
- **WebSocket Streams**: 3 (logs, ev-status, ocpp)
- **Modal Dialogs**: 6
- **Button States**: 7
- **Log File Types**: 3
