# WallboxTester - Functional Specification Document (FSD)

## 1. Overview

### 1.1 Purpose
This document specifies the functional requirements and test procedures for the WallboxTester OCPP 1.6-J test server implementation. The system provides comprehensive testing capabilities for electric vehicle charge points using the Open Charge Point Protocol (OCPP) version 1.6-J.

### 1.2 System Architecture
The WallboxTester is a Python-based OCPP server that provides:
- WebSocket-based OCPP 1.6-J server implementation
- Web UI for test management and monitoring
- EV simulator integration for automated testing
- Real-time logging and status monitoring
- Comprehensive test suite execution

### 1.3 Key Components
- **OCPP Server**: WebSocket server handling charge point connections
- **Test Engine**: Automated test execution and validation
- **EV Simulator**: External EV state simulation for testing
- **Web Interface**: Real-time monitoring and control
- **Transaction Management**: Complete transaction lifecycle handling

## Test Categories and Test Cases

### **A. Core Communication & Status**

#### A.1: Initial Registration
Tests that the charge point has registered itself with the server by triggering a BootNotification.

#### A.2: Get Configuration
Retrieves and analyzes all OCPP configuration keys from the charge point, categorizing them as Core, Optional, or Vendor-specific.

#### A.3: Change Configuration
Tests the ability to modify charge point configuration by changing the HeartbeatInterval to 30 seconds.

#### A.4: Check Initial State
Verifies charge point status detection and EV state transitions (A→B→C→A) with transaction handling.

#### A.5: Trigger All Messages
Tests TriggerMessage functionality for StatusNotification, MeterValues, BootNotification, and other OCPP messages.

#### A.6: Meter Values
Triggers StatusNotification and MeterValues messages to test data acquisition capabilities.

### **B. Authorization & Transaction Management**

#### B.1: Reset Transaction Management
Resets the wallbox to a clean state by clearing all active transactions and setting connector availability to Operative.

#### B.2: Autonomous Start
Tests autonomous transaction initiation without manual authorization. Configures the wallbox for automatic start when an EV connects.

#### B.3: RFID Tap-to-Charge
Tests standard RFID card authorization flow with online authorization. Uses interactive modal with test mode for accepting any RFID card.

#### B.4: Anonymous Remote Start
Tests remote transaction start without RFID card requirement. Initiates charging session remotely without user identification.

#### B.5: Plug-and-Charge
Tests plug-and-charge functionality where charging starts automatically when EV is connected, without RFID or remote start.

#### B.6: Clear RFID Cache
Clears the local authorization list (RFID memory) using OCPP `ClearCache` command. May return "Rejected" if wallbox doesn't support local lists.

#### B.7: Send RFID List
Sends local authorization list with RFID cards (TEST_CARD_001, TEST_CARD_002, TEST_CARD_003) using `SendLocalList`. Returns "NotSupported" if feature unavailable.

#### B.8: Get RFID List Version
Retrieves version of local authorization list using `GetLocalListVersion`. Returns -1 if wallbox doesn't support local authorization lists.

### **X. System Control**

#### X.1: Reboot Wallbox
Performs emergency wallbox reboot using OCPP Reset Hard command. Forces termination of all active transactions and reboots the charge point.

### **C. Smart Charging Profile**

#### C.1: SetChargingProfile (TxProfile) [AUTONOMOUS]
Sets transaction-specific charging profiles with configurable power/current limits, units (W/A), duration, and profile parameters. **Fully autonomous**: Automatically starts transaction if needed, tests profile application, then cleans up (stops transaction, clears profile, resets EV to state A). Can run independently without manual setup. **Includes verification**: After setting the profile, the test automatically verifies the profile was applied correctly by calling GetCompositeSchedule and comparing expected vs actual values (charging rate unit and power limit). Results are displayed in a popup showing OK/NOT OK status for each parameter.

#### C.2: TxDefaultProfile [AUTONOMOUS]
Sets default charging profiles that apply to future transactions at both charge point and connector levels. **Fully autonomous**: Tests profile creation, then clears the TxDefaultProfile at completion. No transaction required, no manual cleanup needed. **Includes verification**: After setting the profile, the test automatically verifies the profile was applied correctly by calling GetCompositeSchedule (at charge point level, connectorId=0) and comparing expected vs actual values (charging rate unit and power limit). Results are displayed in a popup showing OK/NOT OK status for each parameter.

#### C.3: GetCompositeSchedule [AUTONOMOUS]
Retrieves and displays the current composite charging schedule from the charge point to verify active profile application. Shows charging rate unit, periods, limits, and phases. **Read-only operation** - no side effects, no cleanup needed.

#### C.4: ClearChargingProfile [AUTONOMOUS]
Removes specific charging profiles from the charge point (specifically TxDefaultProfile types). **Cleanup operation by nature** - already autonomous, no additional cleanup needed.

#### C.5: Cleanup [AUTONOMOUS]
Comprehensive cleanup test that stops any active transactions, clears all charging profiles, and resets EV simulator state to 'A' (unplugged). Returns PARTIAL status if any step fails. **Master cleanup** for full environment reset.

### **D. Advanced Charging Control**

#### D.1: Set Live Charging Power
Sets charging profiles for active transactions to control power dynamically during charging.

#### D.2: Set Default Charging Profile
Establishes default charging profiles for future transactions.

#### D.3: Smart Charging Capability Test
Comprehensive test that sets a temporary profile and immediately requests the composite schedule to verify smart charging functionality.

#### D.4: Clear Default Charging Profile
Removes default charging profiles from the charge point.

#### D.5: Set Profile 5000W
Sets a specific 5000W charging profile for testing high-power scenarios.

#### D.6: Set High Charging Profile
Sets maximum power charging profiles for testing wallbox limits.

### **E. Extended Transaction Tests**

#### E.1: Real-World Transaction Test
Comprehensive real-world transaction simulation with multiple charging states and profile changes.

#### E.2-E.8: Extended Charging Profile Tests
Various charging profile tests with different amperage settings (6A, 10A, 16A) and transaction management.

#### E.10: Get Composite Schedule
Extended composite schedule testing for complex charging scenarios.

#### E.11: Clear All Profiles
Comprehensive clearing of all charging profiles from the charge point.

## Automated Reactions 🤖

These messages can be handled automatically by a test script. The central system's reaction is predictable and does not require human input.

- **BootNotification:** Can be handled automatically by the test system. Upon receiving this message, the central system should send a `BootNotification.conf` response with the correct configuration.
- **StartTransaction:** Can be handled automatically. The central system should validate the message and send a `StartTransaction.conf` with a unique `transactionId`.
- **Heartbeat:** This message automatically updates the central system's record of the wallbox's status and last seen time. The system's response is an automated `Heartbeat.conf`.
- **StatusNotification:** Automatically updates the wallbox's status within the central system. The central system updates its internal state to reflect the status change (e.g., `Charging`, `Faulted`).
- **MeterValues:** This message automatically updates the meter values in the central system's database for the ongoing transaction.
- **StopTransaction:** Can be handled automatically. The central system finalizes the transaction record and sends a `StopTransaction.conf` in response.
- **Authorize:** Automatically handled using predefined valid ID tags (`test_id_1`, `test_id_2`). Returns `Accepted` for valid tags, `Invalid` for others.

## Implementation Details

This section details the recent feature implementations and bug fixes for the Wallbox Tester.

### 1. Expanded Test Suite

- **A.4 and A.5 Test Integration**: Added comprehensive A.4 (Check Initial State) and A.5 (Trigger All Messages) tests to the frontend control panel.
- **A.6 Meter Values Test**: Renamed and integrated the former B.1 test as A.6 for better categorization.
- **B.3 RFID Authorization**: Enhanced RFID card testing with real-time popup interface and first-card-accepted, subsequent-invalid logic.
- **X.1 Reboot Wallbox**: Added emergency wallbox reboot functionality (formerly "Brutal Stop") with proper UI placement and red styling.
- **Transaction ID Handling Fix**: Fixed A.4 test to properly handle wallbox-assigned transaction IDs per OCPP 1.6 specification.

### 2. Enhanced Charging Profile Management

- **OCPP-Compliant UI**: Updated charging profile modal to hide irrelevant fields for TxDefaultProfile (C.4) per OCPP standard:
  - Profile Purpose field hidden (fixed as TxDefaultProfile)
  - Duration field hidden (TxDefaultProfile should not have duration)
- **Charging Rate Unit Selection**: Added support for both W (Watts) and A (Amperes) in the charging profile modal:
  - User-selectable charging rate unit dropdown
  - Backend integration for unit-specific profile creation
  - Smart defaults with fallback to server configuration
- **Dynamic Parameters**: Enhanced modal allows configuration of `stackLevel`, `chargingProfilePurpose`, `chargingProfileKind`, `chargingRateUnit`, `limit`, and `duration`.

### 3. Transaction Management Improvements

- **Robust Transaction Detection**: Improved transaction lifecycle handling with proper OCPP flow management:
  - RemoteStartTransaction → Authorize → StartTransaction sequence
  - Proper handling of wallbox-assigned transaction IDs
  - Enhanced state transition monitoring (A→B→C→A)
- **EV State Integration**: Better coordination with EV simulator for realistic testing scenarios.

### 4. UI/UX Enhancements

- **Test Organization**: Reorganized tests into logical categories (A: Communication, B: Transactions, C: Smart Charging).
- **Server Controls**: Added dedicated server control area with properly styled Reboot Wallbox and Shutdown Server buttons.
- **Real-time Feedback**: Enhanced status messages and progress tracking for all test operations.
- **OCPP-Compliant Interface**: Modal interfaces now respect OCPP 1.6 standard requirements and constraints.

### 5. RFID Management System (Experimental)

- **OCPP 1.6-J Standard Implementation**: Added complete RFID authorization list management:
  - `ClearCache` command to clear local RFID memory
  - `SendLocalList` command to send RFID cards to wallbox
  - `GetLocalListVersion` command for list synchronization
- **Enhanced RFID Testing**: Improved B.3 RFID Authorization with real-time card detection and status tracking.
- **Graceful Unsupported Handling**: Proper handling of wallboxes that don't support local authorization lists (return version -1).
- **Frontend Integration**: Added B.4, B.5, B.6 tests to Control Panel with experimental flagging.

### 6. Code Quality and Maintenance

- **Logging Cleanup**: Reduced excessive auto-detection and protocol warnings to appropriate debug levels.
- **Comment Cleanup**: Removed redundant and obvious comments while preserving essential OCPP protocol documentation.
- **Error Handling**: Improved graceful shutdown and error recovery mechanisms.
- **OCPP Compliance**: Ensured all implementations follow OCPP 1.6-J specification requirements.

### 7. Test Result Visual Feedback System

- **Enhanced Button States**: Added comprehensive visual feedback for all test result states:
  - Green (`btn-success`): Test passed
  - Red (`btn-failure`): Test failed
  - Yellow (`btn-skipped`): Test skipped
  - Orange (`btn-partial`): Test partially completed
  - Grey (`btn-not-supported`): Feature not supported by wallbox
  - Grey with wait cursor (`btn-running`): Test currently executing
- **Consistent Handling**: Unified test result handling across B.6, B.7, and B.8 for "NotSupported" responses
- **Real-time Updates**: Polling mechanism updates button colors every 3 seconds based on server-side test results
- **User Experience**: Clear visual distinction between test failures (red) and unsupported features (grey)

### 8. C Section Smart Charging Enhancements

- **C.1 Automatic Transaction Management**: Enhanced SetChargingProfile test to automatically start transactions when none exist
  - Sends RemoteStartTransaction if no active transaction detected
  - Waits up to 15 seconds for transaction to start before proceeding
  - Sets EV state to 'C' (charging) automatically
  - **Autonomous cleanup**: Stops transaction, clears profile, and resets EV to state A after test
  - Fully self-contained - no manual setup or cleanup required
- **C.2 TxDefaultProfile Autonomy**: Enhanced to clean up after itself
  - Sets default charging profile for future transactions
  - **Autonomous cleanup**: Clears TxDefaultProfile at end of test
  - Can run independently without affecting other tests
- **C.3 & C.4 Already Autonomous**: GetCompositeSchedule and ClearChargingProfile are read-only/cleanup operations
  - C.3 only queries current schedule (no side effects)
  - C.4 clears profiles (cleanup operation by nature)
- **C.5 Cleanup Test**: Comprehensive cleanup test for resetting entire test environment
  - Stops any active transactions using RemoteStopTransaction
  - Clears all charging profiles from wallbox
  - Resets EV simulator state to 'A' (unplugged)
  - Returns PARTIAL status if any cleanup step fails (vs full FAILED)
  - Provides clear status messages with emoji indicators for each step
- **Full Test Autonomy**: All C section tests are now fully autonomous
  - Each test can run independently without manual setup
  - Tests clean up their own state after completion
  - No dependencies between tests - can run in any order
- **Test Sequence Improvement**: Corrected C section test ordering in documentation to match implementation (C.1: TxProfile, C.2: TxDefaultProfile, C.3: GetCompositeSchedule, C.4: Clear, C.5: Cleanup)

### 9. Charging Profile Verification System

- **Automated Verification for C.1 and C.2**: Enhanced smart charging tests with automatic verification using GetCompositeSchedule
  - After SetChargingProfile command succeeds, automatically calls GetCompositeSchedule to verify profile application
  - 2-second delay before verification to allow wallbox processing time
  - Compares expected vs actual values for charging rate unit and power limit
  - C.1 uses `connectorId=1` for transaction-specific verification
  - C.2 uses `connectorId=0` for charge point level verification
- **Verification Results Storage**: Added VERIFICATION_RESULTS global dictionary in core.py
  - Stores verification data keyed by charge_point_id
  - Contains test name and array of verification results (parameter, expected, actual, status)
- **REST API Endpoint**: Added `/api/verification_results` endpoint
  - Returns verification results for the active charge point
  - Used by frontend to fetch and display verification data
- **Interactive Popup Display**: Enhanced UI with verification results modal
  - Automatically displays after C.1 or C.2 tests complete successfully
  - Shows table with Parameter, Expected, Actual, and Status columns
  - Green "OK" status with checkmark for matching values
  - Red "NOT OK" status with X for mismatched values
  - Styled modal with professional table layout and color-coded status indicators
- **User Experience**: Provides immediate feedback on profile application success
  - Confirms wallbox correctly applied the charging profile
  - Helps diagnose configuration issues if values don't match
  - Only shown when test passes (PASSED status)