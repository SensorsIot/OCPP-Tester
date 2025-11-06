# ⚡ OCPP 1.6-J Wallbox Tester

A comprehensive OCPP 1.6-J test server for validating electric vehicle charge point implementations with real-time monitoring and automated test sequences.

## 📋 Overview

WallboxTester provides a complete suite of OCPP 1.6-J protocol tests through a WebSocket-based server and web interface. It supports individual test execution, automated test sequences with combined logging, and real-time verification of charging profiles.

## ✨ Key Features

- **🔌 Full OCPP 1.6-J Support**: Complete protocol implementation with automated message handling
- **🧪 20+ Individual Tests**: Covering communication, authorization, transactions, and smart charging
- **🤖 Automated Test Sequences**: B All Tests (4 tests) and C All Tests (8 iterations) with comprehensive logging
- **📊 Real-time Monitoring**: WebSocket-streamed logs and live EV status updates
- **✅ Profile Verification**: Automatic verification of charging profiles using GetCompositeSchedule
- **🎨 Visual Feedback**: 7 button states (success/failure/running/skipped/partial/not-supported/disabled)
- **📝 Combined Logging**: GetConfiguration + test parameters + verification results + OCPP messages
- **🚗 EV Simulator Integration**: External EV state simulation for realistic testing

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd ocpp

# Install dependencies
pip install -r requirements.txt

# Start the server
python3 main.py
```

### Access

- **Web UI**: http://localhost:5000
- **OCPP WebSocket**: ws://localhost:8887/{ChargePointId}
- **Log Stream**: ws://localhost:8887/logs
- **EV Status Stream**: ws://localhost:8887/ev-status

## ⚙️ Configuration

Environment variables (defaults in `app/core.py`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OCPP_HOST` | 0.0.0.0 | WebSocket server host |
| `OCPP_PORT` | 8887 | WebSocket server port |
| `HTTP_HOST` | 0.0.0.0 | Web UI server host |
| `HTTP_PORT` | 5000 | Web UI server port |
| `EV_SIMULATOR_BASE_URL` | http://192.168.0.151 | EV simulator service URL |
| `EV_SIMULATOR_CHARGE_POINT_ID` | Wallbox001 | Charge point ID for simulator |

## 📊 Test Categories

### A. Core Communication & Status (6 tests)
- **A.1**: ChangeConfiguration - Modify HeartbeatInterval
- **A.2**: Get All Configuration - Retrieve all config keys
- **A.3**: Get OCPP Standard Keys - Get 35 OCPP 1.6-J standard parameters
- **A.4**: Check Initial State - Test EV state transitions (A→B→C→E)
- **A.5**: Trigger All Messages - Test TriggerMessage functionality
- **A.6**: Status and Meter Value Acquisition - Trigger and wait for MeterValues

### B. Authorization & Transaction Management (8 tests)
- **B.1**: Reset Transaction Management - Reset transaction state
- **B.2**: Autonomous Start - Test autonomous charging
- **B.3**: RFID Tap-to-Charge - Standard authorization flow with modal
- **B.4**: Anonymous Remote Start - RemoteStartTransaction without ID tag
- **B.5**: Plug-and-Charge - Automated charging with pre-authorization
- **B.6**: Clear RFID Cache - ClearCache command
- **B.7**: Send RFID List - SendLocalList command
- **B.8**: Get RFID List Version - GetLocalListVersion command

### C. Smart Charging Profile (4 tests + automated sequence)
- **C.1**: SetChargingProfile - Set TxProfile with verification
- **C.2**: TxDefaultProfile - Set default profile with verification
- **C.3**: GetCompositeSchedule - Retrieve charging schedule
- **C.4**: ClearChargingProfile - Remove charging profiles

### X. System Control (2 tests)
- **X.1**: Reboot Wallbox - OCPP Reset command
- **X.2**: Dump All Configuration - Export config to log file

## 🤖 Automated Test Sequences

### B All Tests
Runs B.2 → B.3 → B.4 → B.5 sequentially.

**Features**:
- GetConfiguration called at start
- Combined log with config, test results, and OCPP messages
- Frontend-driven (supports B.3 modal)
- 10-minute timeout
- Result summary popup

**Log Location**: `/home/ocpp/logs/b_all_tests_{charge_point_id}_{timestamp}.log`

### C All Tests
Runs C.1 and C.2 tests 4 times each (8 iterations total).

**Test Levels**: disable (0A/0W), low (6A/4000W), medium (10A/8000W), high (16A/11000W)

**Features**:
- GetConfiguration called at start
- Comprehensive log with config, test parameters, verification results, and OCPP messages
- Backend-driven (single API call)
- 8-minute timeout
- Verification for all 8 iterations

**Log Location**: `/home/ocpp/logs/c_all_tests_{charge_point_id}_{timestamp}.log`

## ✅ Verification System

C.1 and C.2 tests automatically verify profile application:
1. SetChargingProfile command sent
2. 2-second delay for wallbox processing
3. GetCompositeSchedule called to verify
4. Expected vs actual comparison
5. Verification results displayed in modal

**Verified Parameters**:
- Profile Purpose (TxProfile / TxDefaultProfile)
- Stack Level (0)
- Profile Kind (Absolute)
- Transaction ID (C.1 only)
- Charging Rate Unit (W / A)
- Power Limit (value)
- Duration (C.1 only)
- Number of Phases (1 / 3)

**Test Fails** if GetCompositeSchedule shows incorrect values.

## 🎨 Visual Feedback

Button states:
- 🔵 **Blue**: Not run yet
- 🟢 **Green**: Test PASSED
- 🔴 **Red**: Test FAILED
- ⚫ **Grey + cursor**: Currently executing
- 🟡 **Yellow**: Test SKIPPED
- 🟠 **Orange**: Partial success
- ⚫ **Grey**: Feature not supported / Disabled

Colors persist across page refreshes and update every 3 seconds via polling.

## 📝 Log Files

### Individual Test Logs
```
/home/ocpp/logs/{test_name}_{charge_point_id}_{timestamp}.log
```
Contains: Test name, parameters, OCPP messages, result

### Combined Test Logs
```
/home/ocpp/logs/b_all_tests_{charge_point_id}_{timestamp}.log
/home/ocpp/logs/c_all_tests_{charge_point_id}_{timestamp}.log
```

Structure:
1. **Configuration Section**: Complete GetConfiguration results
2. **Test Parameters**: Detailed test configuration (C All Tests only)
3. **Test Results Summary**: Pass/fail status for each test
4. **Verification Results**: Expected vs actual comparison (C All Tests only)
5. **OCPP Messages**: Timestamped request/response pairs

## 🏗️ Architecture

```
main.py                     # Entry point & WebSocket routing
├── app/
│   ├── core.py            # Global state & configuration
│   ├── ocpp_handler.py    # WebSocket connection management
│   ├── ocpp_server_logic.py # OCPP message processing
│   ├── ocpp_message_handlers.py # Individual message handlers
│   ├── ocpp_test_steps.py # Test implementations
│   ├── messages.py        # OCPP message payloads (dataclasses)
│   ├── web_ui_server.py   # Flask REST API
│   ├── ev_simulator_manager.py # EV simulator integration
│   ├── streamers.py       # WebSocket streaming (logs, EV status)
│   └── templates/
│       └── index.html     # Web UI
```

## 📡 API Endpoints

### Test Execution
- `POST /api/test/<step_name>` - Run individual test
- `POST /api/test/b_all_tests` - Run B All Tests
- `POST /api/test/c_all_tests` - Run C All Tests
- `POST /api/test/get_configuration` - Call GetConfiguration
- `POST /api/test/combine_logs` - Combine multiple log files

### System Control
- `GET/POST /api/charging_rate_unit` - Get/set charging rate unit
- `GET /api/charge_points` - Get all charge points
- `POST /api/set_active_charge_point` - Set active charge point
- `POST /api/clear_test_results` - Clear all test results
- `POST /api/shutdown` - Shutdown server

### EV Simulator
- `GET /api/ev_status` - Get EV simulator status
- `POST /api/set_ev_state` - Set EV state (A/B/C/E)

### RFID Test Mode
- `POST /api/enable_rfid_test_mode` - Enable RFID test mode
- `POST /api/disable_rfid_test_mode` - Disable RFID test mode
- `GET /api/rfid_status` - Get RFID test mode status

### Data Retrieval
- `GET /api/verification_results?test=C1|C2` - Get verification results
- `GET /api/transactions` - Get transaction history
- `GET /api/test/get_latest_log?test_name=<name>` - Get latest log file

## 🚗 EV Simulator Integration

When enabled, displays real-time EV state:
- **State**: A (Disconnected), B (Connected), C (Charging), E (Error)
- **Wallbox Advertised Current** (A)
- **CP Voltage** (V)
- **CP Duty Cycle** (%)
- **PP Voltage** (V)
- **Error Status**

Control buttons: Set State A / B / C / E

## 🎯 RFID Test Mode

Enabled automatically during B.3 Tap-to-Charge test:
- **First card**: Always ACCEPTED
- **Subsequent cards**: Always INVALID
- Tracks card presentation order
- Allows testing with any RFID card

## 📦 Requirements

- Python 3.11+
- websockets
- flask
- uvicorn
- requests
- aiohttp

Install via: `pip install -r requirements.txt`

## 📚 Documentation

- **WallboxTester-FSD.md**: Complete functional specification with detailed test descriptions
- **CLAUDE.md**: Development guidelines and codebase overview

## 🔍 OCPP Message Handling

### Automated Reactions
- **BootNotification**: Sends BootNotification.conf
- **StartTransaction**: Validates and assigns transaction ID
- **Heartbeat**: Updates last seen time
- **StatusNotification**: Updates connector status
- **MeterValues**: Updates transaction data
- **StopTransaction**: Finalizes transaction
- **Authorize**: Returns Accepted/Invalid based on ID tag

### Test-Initiated Commands
- GetConfiguration, ChangeConfiguration
- RemoteStartTransaction, RemoteStopTransaction
- SetChargingProfile, GetCompositeSchedule, ClearChargingProfile
- Reset, TriggerMessage
- ClearCache, SendLocalList, GetLocalListVersion

## 📊 System Statistics

- **Total Tests**: 20 individual + 2 automated sequences
- **Test Iterations**: 12 (B All: 4, C All: 8)
- **API Endpoints**: 20+
- **WebSocket Streams**: 3 (logs, ev-status, ocpp)
- **Button States**: 7
- **Modal Dialogs**: 6

## 📄 License

See repository license file.
