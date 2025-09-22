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

## 2. Test Categories and Test Cases

### 2.1 Category A: Basic Functionality Tests

#### A.1 Initial Registration (`run_a1_initial_registration`)
**Purpose**: Verifies that the charge point has registered itself and responds to server commands.

**OCPP Commands Used**:
- `TriggerMessage` → `BootNotification`

**Test Procedure**:
1. Send TriggerMessage request for BootNotification
2. Verify charge point acknowledges the request
3. Confirm charge point is responsive to server-initiated commands

**Expected Result**: Charge point responds with acknowledgment

---

#### A.2 Configuration Exchange (`run_a2_configuration_exchange`)
**Purpose**: Fetches and displays all configuration settings from the charge point.

**OCPP Commands Used**:
- `GetConfiguration` (with empty key list to fetch all keys)

**Test Procedure**:
1. Send GetConfiguration request with empty key array
2. Parse and display all configuration keys
3. Extract SupportedFeatureProfiles for capability detection
4. Log all key-value pairs with readonly status

**Expected Result**: Complete configuration profile retrieved and logged

---

#### A.3 Change Configuration Test (`run_a3_change_configuration_test`)
**Purpose**: Changes multiple configuration keys to match EVCC log requirements.

**OCPP Commands Used**:
- `ChangeConfiguration` (multiple calls for different keys)

**Configuration Keys Modified**:
- `MeterValuesSampledData`: "Current.Import.L1,Current.Import.L2,Current.Import.L3,Power.Active.Import.L1,Power.Active.Import.L2,Power.Active.Import.L3,Energy.Active.Import.Register,Voltage.L1-N,Voltage.L2-N,Voltage.L3-N"
- `MeterValueSampleInterval`: "10"
- `WebSocketPingInterval`: "30"
- `AuthorizeRemoteTxRequests`: "true"
- `HeartbeatInterval`: "10"
- `OCPPCommCtrlrMessageAttemptIntervalBoo`: "5"
- `TxCtrlrTxStartPoint`: "Authorization"
- `FreeChargeMode`: "true"

**Test Procedure**:
1. For each configuration key, send ChangeConfiguration request
2. Verify each change is accepted
3. Report success/failure for each key

**Expected Result**: All configuration changes accepted

---

#### A.4 Check Initial State (`run_a4_check_initial_state`)
**Purpose**: Tests EV state transitions and corresponding charge point status changes.

**OCPP Commands Used**:
- Status monitoring (via StatusNotification messages)

**EV Simulator States Tested**:
- State A → Available
- State B → Preparing
- State C → Charging
- State E → Faulted
- Return to State A → Available

**Test Procedure**:
1. Set EV simulator to each state sequentially
2. Wait for corresponding StatusNotification from charge point
3. Verify correct status transitions
4. Validate 15-second timeout for each transition

**Expected Result**: All state transitions occur within timeout

---

#### A.5 Trigger All Messages Test (`run_a5_trigger_all_messages_test`)
**Purpose**: Tests all TriggerMessage functionalities supported by the charge point.

**OCPP Commands Used**:
- `TriggerMessage` for each supported message type

**Messages Triggered**:
- `BootNotification`: {}
- `DiagnosticsStatusNotification`: {}
- `FirmwareStatusNotification`: {}
- `Heartbeat`: {}
- `MeterValues`: {"connectorId": 1}
- `StatusNotification`: {"connectorId": 1}

**Test Procedure**:
1. Check if RemoteTrigger feature is supported
2. For each message type, send TriggerMessage request
3. Verify charge point acknowledges each trigger
4. Skip test if RemoteTrigger not supported

**Expected Result**: All trigger requests acknowledged

### 2.2 Category B: Status and Meter Value Tests

#### B.1 Status and Meter Value Acquisition (`run_b1_status_and_meter_value_acquisition`)
**Purpose**: Requests meter values and waits for them to be received.

**OCPP Commands Used**:
- `TriggerMessage` → `MeterValues`

**Test Procedure**:
1. Create event to wait for MeterValues message
2. Send TriggerMessage for MeterValues on connector 1
3. Wait up to 15 seconds for triggered MeterValues message
4. Verify message is received

**Expected Result**: MeterValues message received within timeout

### 2.3 Category C: Transaction Management Tests

#### C.1 Remote Transaction Test (`run_c1_remote_transaction_test`)
**Purpose**: Starts and stops a complete transaction remotely.

**OCPP Commands Used**:
- `RemoteStartTransaction`
- `RemoteStopTransaction`
- `ClearChargingProfile`
- `SetChargingProfile` (with disable profile)

**Test Procedure**:
1. Set EV state to B (Preparing)
2. Clear any existing charging profiles
3. Send RemoteStartTransaction with disable charging profile (0W/0A limit)
4. Wait for charge point to report "Charging" status
5. Set EV state to C to simulate charging
6. Monitor advertised current and duty cycle from EV simulator
7. Let transaction run for 10 seconds
8. Send RemoteStopTransaction
9. Clean up by setting EV state to A

**Expected Result**: Complete remote start/stop cycle successful

---

#### C.2 User Initiated Transaction Test (`run_c2_user_initiated_transaction_test`)
**Purpose**: Manual test step for user-initiated transactions.

**OCPP Commands Used**: None (manual test)

**Test Procedure**:
1. Display instructions for manual ID tag presentation
2. Wait for StartTransaction message from charge point

**Expected Result**: Manual step completion

---

#### C.3 Check Power Limits Test (`run_c3_check_power_limits_test`)
**Purpose**: Checks current power/current limits using GetCompositeSchedule.

**OCPP Commands Used**:
- `GetCompositeSchedule`

**Test Procedure**:
1. Send GetCompositeSchedule request for connector 1
2. Parse and display active charging schedule
3. Show charging rate unit, periods, and limits
4. Verify response within 30-second timeout

**Expected Result**: Current charging limits retrieved and displayed

### 2.4 Category D: Smart Charging Tests

#### D.1 Set Live Charging Power (`run_d1_set_live_charging_power`)
**Purpose**: Sets a charging profile to limit power on an active transaction.

**OCPP Commands Used**:
- `ClearChargingProfile`
- `SetChargingProfile` (TxProfile with disable limit)

**Test Procedure**:
1. Verify ongoing transaction exists
2. Set EV state to C
3. Clear existing profiles
4. Set TxProfile with disable charging value (0W/0A)
5. Verify profile acceptance

**Expected Result**: Charging profile applied to active transaction

---

#### D.2 Set Default Charging Profile (`run_d2_set_default_charging_profile`)
**Purpose**: Sets a default charging profile for future transactions.

**OCPP Commands Used**:
- `ClearChargingProfile`
- `SetChargingProfile` (TxDefaultProfile for connectorId=0 and connectorId=1)

**Test Procedure**:
1. Clear existing profiles
2. Set TxDefaultProfile for charge point level (connectorId=0)
3. Set TxDefaultProfile for connector level (connectorId=1)
4. Use medium charging value with 3-phase configuration
5. Set startSchedule to current time minus 1 minute

**Expected Result**: Default profiles set for both levels

---

#### D.3 Smart Charging Capability Test (`run_d3_smart_charging_capability_test`)
**Purpose**: Placeholder for complex smart charging tests.

**OCPP Commands Used**: None

**Test Procedure**:
1. Log placeholder status
2. Mark as passed

**Expected Result**: Test marked as successful (placeholder)

---

#### D.4 Clear Default Charging Profile (`run_d4_clear_default_charging_profile`)
**Purpose**: Clears any default charging profiles.

**OCPP Commands Used**:
- `ClearChargingProfile` (TxDefaultProfile)

**Test Procedure**:
1. Send ClearChargingProfile for connectorId=0 with TxDefaultProfile purpose
2. Verify clearance acknowledgment

**Expected Result**: Default profiles cleared

---

#### D.5 Set Profile 5000W (`run_d5_set_profile_5000w`)
**Purpose**: Sets a charging profile to medium power/current.

**OCPP Commands Used**:
- `ClearChargingProfile`
- `SetChargingProfile` (ChargePointMaxProfile)

**Test Procedure**:
1. Clear existing profiles
2. Set ChargePointMaxProfile for connectorId=0
3. Use medium charging value
4. Verify profile acceptance

**Expected Result**: Medium power profile applied

---

#### D.6 Set High Charging Profile (`run_d6_set_high_charging_profile`)
**Purpose**: Sets a default charging profile to high power/current.

**OCPP Commands Used**:
- `ClearChargingProfile`
- `SetChargingProfile` (TxDefaultProfile for both levels)

**Test Procedure**:
1. Clear existing profiles
2. Set high charging value TxDefaultProfile for connectorId=0 and connectorId=1
3. Use 3-phase configuration
4. Set startSchedule to current time minus 1 minute

**Expected Result**: High power default profiles set

### 2.5 Category E: Extended Transaction Tests

#### E.1 Remote Start State A (`run_e1_remote_start_state_a`)
**Purpose**: Attempts RemoteStartTransaction from EV state A (Available).

**OCPP Commands Used**:
- `RemoteStartTransaction`

**Test Procedure**:
1. Set EV state to A
2. Send RemoteStartTransaction
3. Expect acceptance and transition to Preparing
4. Clean up by returning to state A

**Expected Result**: Remote start accepted from Available state

---

#### E.2 Remote Start State B (`run_e2_remote_start_state_b`)
**Purpose**: Tests RemoteStartTransaction from EV state B (Preparing).

**OCPP Commands Used**:
- `RemoteStartTransaction`

**Test Procedure**:
1. Set EV state to B
2. Check for auto-started transactions
3. Send RemoteStartTransaction
4. Handle acceptance or rejection due to auto-start
5. Set EV state to C for charging simulation

**Expected Result**: Remote start handled appropriately

---

#### E.3 Remote Start State C (`run_e3_remote_start_state_c`)
**Purpose**: Tests RemoteStartTransaction from EV state C (Charging).

**OCPP Commands Used**:
- `RemoteStartTransaction`

**Test Procedure**:
1. Set EV state to C
2. Check for auto-started transactions
3. Send RemoteStartTransaction
4. Handle acceptance or rejection scenarios
5. Maintain charging state

**Expected Result**: Remote start handled from charging state

---

#### E.4 Set Profile 6A (`run_e4_set_profile_6a`)
**Purpose**: Sets a low-level charging profile for active transaction.

**OCPP Commands Used**:
- `SetChargingProfile` (TxProfile with low limit)

**Test Procedure**:
1. Verify active transaction exists
2. Set TxProfile with low charging value
3. Use stackLevel=2 for transaction override

**Expected Result**: Low power profile applied to transaction

---

#### E.5 Set Profile 10A (`run_e5_set_profile_10a`)
**Purpose**: Sets a medium-level TxProfile for active charging session.

**OCPP Commands Used**:
- `ClearChargingProfile`
- `SetChargingProfile` (TxProfile)
- `GetCompositeSchedule` (verification)

**Test Procedure**:
1. Verify active transaction
2. Clear existing profiles
3. Set TxProfile with medium charging value
4. Verify with GetCompositeSchedule
5. Confirm effective limit is active

**Expected Result**: Medium power TxProfile verified via composite schedule

---

#### E.6 Set Profile 16A (`run_e6_set_profile_16a`)
**Purpose**: Sets a high-level charging profile for active transaction.

**OCPP Commands Used**:
- `ClearChargingProfile`
- `SetChargingProfile` (TxProfile with high limit)

**Test Procedure**:
1. Verify active transaction
2. Clear existing profiles
3. Set TxProfile with high charging value
4. Use stackLevel=0

**Expected Result**: High power profile applied

---

#### E.7 Clear Profile (`run_e7_clear_profile`)
**Purpose**: Clears default charging profiles during active transaction.

**OCPP Commands Used**:
- `ClearChargingProfile` (TxDefaultProfile)

**Test Procedure**:
1. Clear TxDefaultProfile for connectorId=0
2. Maintain active transaction state

**Expected Result**: Default profiles cleared without affecting transaction

---

#### E.8 Remote Stop Transaction (`run_e8_remote_stop_transaction`)
**Purpose**: Stops the active transaction remotely.

**OCPP Commands Used**:
- `RemoteStopTransaction`

**Test Procedure**:
1. Identify active transaction
2. Send RemoteStopTransaction with transaction ID
3. Verify stop acknowledgment

**Expected Result**: Active transaction stopped remotely

---

#### E.9 Brutal Stop (`run_e9_brutal_stop`)
**Purpose**: Forces immediate stop via Hard Reset.

**OCPP Commands Used**:
- `Reset` (Hard)

**Test Procedure**:
1. Send Reset Hard request
2. Expect charge point reboot
3. Anticipate late StopTransaction messages after reconnect

**Expected Result**: Hard reset executed, charge point reboots

---

#### E.10 Get Composite Schedule (`run_e10_get_composite_schedule`)
**Purpose**: Queries current charging schedule on connector 1.

**OCPP Commands Used**:
- `GetCompositeSchedule`

**Test Procedure**:
1. Request composite schedule for 1 hour duration
2. Parse and display active schedule details
3. Show charging periods and limits

**Expected Result**: Current schedule retrieved and displayed

---

#### E.11 Clear All Profiles (`run_e11_clear_all_profiles`)
**Purpose**: Clears ALL charging profiles from the charge point.

**OCPP Commands Used**:
- `ClearChargingProfile` (connectorId=0)
- `ClearChargingProfile` (connectorId=1)

**Test Procedure**:
1. Clear all profiles for connectorId=0
2. Clear all profiles for connectorId=1
3. Handle NotSupported status gracefully

**Expected Result**: All charging profiles cleared

## 3. OCPP Message Reference

### 3.1 Core Messages
- **BootNotification**: Charge point registration
- **StatusNotification**: Connector status updates
- **Heartbeat**: Keep-alive messages
- **Authorize**: ID tag authorization
- **StartTransaction**: Transaction initiation
- **StopTransaction**: Transaction completion
- **MeterValues**: Energy/power measurements

### 3.2 Configuration Messages
- **GetConfiguration**: Retrieve configuration keys
- **ChangeConfiguration**: Modify configuration values

### 3.3 Remote Control Messages
- **RemoteStartTransaction**: Server-initiated transaction start
- **RemoteStopTransaction**: Server-initiated transaction stop
- **TriggerMessage**: Request specific message from charge point
- **Reset**: Charge point reboot (Soft/Hard)

### 3.4 Smart Charging Messages
- **SetChargingProfile**: Apply charging power limits
- **ClearChargingProfile**: Remove charging profiles
- **GetCompositeSchedule**: Query effective charging schedule

## 4. Configuration Parameters

### 4.1 Meter Value Configuration
- **MeterValuesSampledData**: Specifies which measurements to include
- **MeterValueSampleInterval**: Frequency of meter value reports (seconds)

### 4.2 Communication Configuration
- **HeartbeatInterval**: Heartbeat frequency (seconds)
- **WebSocketPingInterval**: WebSocket ping frequency (seconds)

### 4.3 Authorization Configuration
- **AuthorizeRemoteTxRequests**: Enable remote transaction authorization
- **FreeChargeMode**: Allow charging without authorization

### 4.4 Transaction Configuration
- **TxCtrlrTxStartPoint**: When transactions start ("Authorization")

## 5. EV Simulator States

### 5.1 State Mapping
- **State A**: Available (EV disconnected)
- **State B**: Preparing (EV connected, not charging)
- **State C**: Charging (EV connected and drawing power)
- **State E**: Faulted (Error condition)

### 5.2 Status Correlation
Each EV simulator state corresponds to expected charge point status:
- A → Available
- B → Preparing
- C → Charging
- E → Faulted

## 6. Charging Profile Types

### 6.1 Profile Purposes
- **ChargePointMaxProfile**: Maximum power limit for entire charge point
- **TxDefaultProfile**: Default limits for future transactions
- **TxProfile**: Specific limits for individual transactions

### 6.2 Profile Hierarchy
- **stackLevel**: Priority level (0 = highest priority)
- **connectorId**: Target connector (0 = charge point level)

### 6.3 Rate Units
- **W**: Watts (power-based limiting)
- **A**: Amperes (current-based limiting)

## 7. Test Execution Flow

### 7.1 Sequential Execution
Tests are organized in logical categories and executed in sequence:
1. **Category A**: Basic functionality and configuration
2. **Category B**: Status and meter value handling
3. **Category C**: Core transaction management
4. **Category D**: Smart charging capabilities
5. **Category E**: Extended transaction scenarios

### 7.2 Result Tracking
Each test maintains status:
- **PASSED**: Test completed successfully
- **FAILED**: Test did not meet expected criteria
- **SKIPPED**: Test not applicable (e.g., feature not supported)

### 7.3 Cleanup Procedures
Most tests include cleanup steps:
- Return EV simulator to state A
- Clear charging profiles
- Reset configuration to defaults

## 8. Error Handling

### 8.1 Timeout Management
All OCPP requests include timeouts:
- Standard requests: 15-30 seconds
- Configuration requests: 30 seconds
- State transitions: 15 seconds

### 8.2 Cancellation Support
Tests support cancellation:
- Check cancellation points throughout execution
- Clean up resources on cancellation
- Maintain system state consistency

### 8.3 Feature Detection
Tests adapt based on charge point capabilities:
- Check SupportedFeatureProfiles
- Skip unsupported features
- Handle NotSupported responses gracefully

---

*This document represents the complete functional specification for the WallboxTester OCPP 1.6-J test server implementation. It defines all test cases, OCPP commands, and expected behaviors for comprehensive charge point testing.*