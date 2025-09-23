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

### **B. Transaction Management & Control**

#### B.1: Remote Start Transaction
Tests remote initiation of charging transactions with proper EV state simulation.

#### B.2: Remote Stop Transaction
Tests remote termination of active charging transactions.

#### B.3: Reboot Wallbox
Performs emergency wallbox reboot using OCPP Reset Hard command.

### **C. Smart Charging Profile**

#### C.1: SetChargingProfile (TxProfile)
Sets transaction-specific charging profiles with configurable power/current limits, units (W/A), duration, and profile parameters.

#### C.2: Get Composite Schedule
Retrieves the current composite charging schedule from the charge point to verify profile application.

#### C.3: Clear Charging Profile
Removes specific charging profiles from the charge point.

#### C.4: TxDefaultProfile
Sets default charging profiles that apply to future transactions at both charge point and connector levels.

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

## V2 Implementation Details

This section details the recent feature implementations and bug fixes for the Wallbox Tester.

### 1. Expanded Test Suite

- **A.4 and A.5 Test Integration**: Added comprehensive A.4 (Check Initial State) and A.5 (Trigger All Messages) tests to the frontend control panel.
- **A.6 Meter Values Test**: Renamed and integrated the former B.1 test as A.6 for better categorization.
- **B.3 Reboot Wallbox**: Added emergency wallbox reboot functionality (formerly "Brutal Stop") with proper UI placement and styling.
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

### 5. Code Quality and Maintenance

- **Logging Cleanup**: Reduced excessive auto-detection and protocol warnings to appropriate debug levels.
- **Comment Cleanup**: Removed redundant and obvious comments while preserving essential OCPP protocol documentation.
- **Error Handling**: Improved graceful shutdown and error recovery mechanisms.
- **OCPP Compliance**: Ensured all implementations follow OCPP 1.6-J specification requirements.