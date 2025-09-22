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

## Initial connection to wallbox



2. ## Test Categories and Test Cases

### **A. Core Communication & Status**

#### A.1: `ChangeConfiguration`

####  A.2: `GetConfiguration`

### **B. Authorization & Transaction Management**

#### B.1: `RemoteStartTransaction` 

#### B.2: `RemoteStopTransaction`

### **C. Smart Charging Profile**

#### C.1: `SetChargingProfile` 

#### C.2: `GetCompositeSchedule`

####  C.3: `ClearChargingProfile` 

#### C.4: `TxDefaultProfile`

## Automated Reactions 🤖

These messages can be handled automatically by a test script. The central system's reaction is predictable and does not require human input.

- **BootNotification:** Can be handled automatically by the test system. Upon receiving this message, the central system should send a `BootNotification.conf` response with the correct configuration.
- **StartTransaction:** Can be handled automatically. The central system should validate the message and send a `StartTransaction.conf` with a unique `transactionId`.
- **Heartbeat:** This message automatically updates the central system's record of the wallbox's status and last seen time. The system's response is an automated `Heartbeat.conf`.
- **StatusNotification:** Automatically updates the wallbox's status within the central system. The central system updates its internal state to reflect the status change (e.g., `Charging`, `Faulted`).
- **MeterValues:** This message automatically updates the meter values in the central system's database for the ongoing transaction.
- **StopTransaction:** Can be handled automatically. The central system finalizes the transaction record and sends a `StopTransaction.conf` in response.

### Human-in-the-Loop Reactions 👤

This message requires a human operator to review the request content and make a decision, which is crucial for testing various authorization scenarios.

- **Authorize:** A popup must present the request content (e.g., the `idTag`) and offer the test operator possible answers, such as `Accepted`, `Invalid`, or `Blocked`. The central system's response is based on the operator's decision.



## V2 Implementation Details

This section details the recent feature implementations and bug fixes for the Wallbox Tester.

### 1. Robustness of Test Suite

- **`RemoteStartTransaction` Test Fix**: The test suite has been made more robust by adding a wait for the charge point to become "Available" after a `RemoteStopTransaction` test. This prevents race conditions where a new transaction is started before the charge point is ready, which previously caused the `RemoteStartTransaction` test to fail.

### 2. Interactive Charging Profile Tests

- **UI for `SetChargingProfile`**: A user-friendly pop-up modal has been added to the web UI for the `SetChargingProfile` (C.1) and `TxDefaultProfile` (C.4) tests.
- **Dynamic Parameters**: This modal allows the user to dynamically enter parameters such as `stackLevel`, `chargingProfilePurpose`, `chargingProfileKind`, and `limit` before running the test.
- **Backend Support**: The backend has been updated to receive these parameters and apply them to the `SetChargingProfile` command.

### 3. `SetChargingProfile` Bug Fixes

- **`TxDefaultProfile` Fix**: The `run_c4_tx_default_profile_test` has been fixed to align with the behavior of the tested charge point. The `startSchedule` parameter has been removed, and the default `stackLevel` has been adjusted to `0`, which resolved rejections of the command.
- **Enum Handling**: A bug was fixed where string values for enums were incorrectly being used with subscripting, causing a `TypeError`. The code now correctly uses the string values directly.

### 4. Enhanced UI for Smart Charging

- **`GetCompositeSchedule` Display**: The result of the `GetCompositeSchedule` test is now displayed in the "Live MeterValues Data" window in the UI.
- **Two-Column Layout**: The "Live MeterValues Data" window has been updated to a two-column layout, with `MeterValues` on the left and the `CompositeSchedule` on the right, providing a clearer and more organized view of the charging data.
- **Contextual Dropdown**: The "Profile Purpose" dropdown in the `SetChargingProfile` modal is now context-aware. For the C.1 test, the `TxDefaultProfile` option is hidden, as it is not applicable.