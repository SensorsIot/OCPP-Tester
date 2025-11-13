# Claude Code Development Notes

This file documents important workflows and procedures for developing the OCPP Tester with Claude Code.

## Version Management

### How to Start a New Version

To ensure you're always running the latest code and can track which version is active:

1. **Kill all Python programs**
   ```bash
   pkill -9 -f python
   # Wait a moment
   sleep 2
   # Verify all stopped
   ps aux | grep python | grep -v grep
   ```

2. **Increase the version number in code**

   Edit `app/version.py`:
   ```python
   __version__ = "1.2.0"  # Increment this
   __build_date__ = "2025-11-13"  # Update date

   # Update module versions if those changed
   __test_helpers_version__ = "1.1.0"
   __test_series_b_version__ = "1.3.0"  # Example increment

   # Add changelog entry
   CHANGELOG = {
       "1.2.0": {
           "date": "2025-11-13",
           "changes": [
               "Description of what changed",
               "Another change",
           ]
       },
       # ... previous versions
   }
   ```

3. **Start the program**
   ```bash
   cd /home/ocpp-tester
   nohup ./venv/bin/python3 ocpp-tester.py >> /tmp/restart.log 2>&1 &
   # Wait for startup
   sleep 5
   ```

4. **Check version number**

   **Method 1: Via API**
   ```bash
   curl -s http://localhost:5000/api/version | python3 -m json.tool
   ```

   **Method 2: From test logs**
   ```bash
   # Run any test, check the log for:
   # "Code version: v1.1.0 (2025-11-13)"
   tail -100 /tmp/restart.log | grep "Code version"
   ```

   **Method 3: From startup banner**
   ```bash
   tail -100 /tmp/restart.log | grep "OCPP Tester v"
   ```

### Why Version Management is Important

- **Prevents running old code**: Ensures code changes are actually loaded
- **Debugging**: Know exactly which version produced which test results
- **Tracking changes**: Clear history of what was fixed when
- **Collaboration**: Everyone knows which version they're testing

### Version Numbering Convention

Use semantic versioning: `MAJOR.MINOR.PATCH`

- **MAJOR**: Breaking changes (e.g., 1.0.0 → 2.0.0)
- **MINOR**: New features, non-breaking changes (e.g., 1.1.0 → 1.2.0)
- **PATCH**: Bug fixes (e.g., 1.1.0 → 1.1.1)

Examples:
- Fixed a test bug: `1.1.0` → `1.1.1`
- Added new helper function: `1.1.0` → `1.2.0`
- Changed test framework entirely: `1.x.x` → `2.0.0`

---

## Test B.1 Development History

### Version 1.1.0 (2025-11-13)

**Major Fix: Added Missing State C Transition**

The test was failing because it only set State B (cable connected) but never set State C (vehicle requesting power). The wallbox waits for State C before sending StartTransaction.

**Changes:**
- Added `set_ev_state_and_wait_for_status()` helper
- Added State B → State C transition after cable connection
- Waits for wallbox confirmation at each step
- Added parameter validation before test

**Key code addition:**
```python
# After State B confirmation
success_c, message_c = await set_ev_state_and_wait_for_status(
    self.ocpp_server_logic,
    self.charge_point_id,
    ev_state="C",
    expected_status="Charging",
    timeout=15.0
)
```

**Test flow now:**
1. Validate OCPP parameters
2. Wait for RFID tap
3. Set State B (cable) → Wait for "Preparing"
4. Set State C (power request) → Wait for "Charging"
5. Transaction starts ✓

---

## Helper Functions Added

### `ensure_test_configuration()`
**Location:** `app/test_helpers.py`

Validates and sets multiple OCPP parameters before a test runs.

**Usage:**
```python
required_params = [
    {"key": "LocalPreAuthorize", "value": "false", "description": "Wait for backend authorization"},
    {"key": "LocalAuthorizeOffline", "value": "false", "description": "No offline start"},
]

success, message = await ensure_test_configuration(
    self.handler,
    required_params,
    test_name="B.1 RFID Authorization Before Plug-in"
)

if not success:
    logger.error(f"❌ Test prerequisites not met: {message}")
    self._set_test_result(step_name, "FAILED")
    return
```

### `set_ev_state_and_wait_for_status()`
**Location:** `app/test_helpers.py`

Sets EV simulator state and waits for wallbox to confirm the status change.

**Usage:**
```python
success, message = await set_ev_state_and_wait_for_status(
    self.ocpp_server_logic,
    self.charge_point_id,
    ev_state="B",
    expected_status="Preparing",
    timeout=15.0
)

if success:
    logger.info("✅ Wallbox confirmed state")
else:
    logger.warning(f"⚠️ {message}")
```

**Why this is important:**
- Prevents race conditions
- Ensures wallbox has processed state changes
- Returns clear success/failure status
- Provides timeout protection

---

## Common Issues and Solutions

### Issue: Changes not reflected after editing code

**Symptom:** Test behaves the same way despite code changes

**Solution:** Python processes cache imported modules. Kill all Python and restart:
```bash
pkill -9 -f python && sleep 2
cd /home/ocpp-tester && nohup ./venv/bin/python3 ocpp-tester.py >> /tmp/restart.log 2>&1 &
```

### Issue: Test shows old version number

**Symptom:** Version check shows old version after updating `version.py`

**Cause:** Python process not restarted or wrong version file being read

**Solution:**
1. Verify version.py was actually edited
2. Kill all Python processes
3. Restart and verify with API: `curl http://localhost:5000/api/version`

### Issue: RFID tap detected too early

**Symptom:** Modal appears but test hasn't started parameter validation yet

**Cause:** Frontend enables RFID mode before backend is ready

**Solution:** Wait for log message "⏳ Waiting for RFID card tap" before tapping

**Code fix applied in v1.1.0:**
```python
# Clear any stale RFID data from early taps (before test was ready)
CHARGE_POINTS[self.charge_point_id]["accepted_rfid"] = None
```

---

## Git Workflow

### Committing Changes

Always use descriptive commit messages:

```bash
cd /home/ocpp-tester
git add <files>
git commit -m "$(cat <<'EOF'
Brief summary of changes

Detailed description:
- What was changed
- Why it was changed
- Impact on tests

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

### Pushing to Remote

If using HTTPS (requires authentication):
```bash
git push
# Enter GitHub username and password/token when prompted
```

If using SSH (recommended):
```bash
git remote set-url origin git@github.com:SensorsIot/OCPP-Tester.git
git push
```

---

## Testing Workflow

### Before Running a Test

1. ✅ Check version: `curl http://localhost:5000/api/version`
2. ✅ Verify wallbox connected: `curl http://localhost:5000/api/charge_points`
3. ✅ Check logs are accessible: `tail -f /tmp/restart.log`

### Running Test B.1

1. Start test via API or UI
2. **Wait for preparation to complete** (5-10 seconds)
3. Look for message: "⏳ Waiting for RFID card tap"
4. **Now tap RFID card**
5. Wait for transaction to start
6. Check results in logs

### After a Test

1. Check test result: PASSED or FAILED
2. Review logs: `tail -100 /tmp/restart.log`
3. Check detailed log: `/home/ocpp-tester/logs/run_b1_rfid_public_charging_test_Actec_*.log`
4. Verify version was logged correctly

---

## Troubleshooting

### Check if tester is running
```bash
ps aux | grep ocpp-tester.py | grep -v grep
```

### Check recent logs
```bash
tail -50 /tmp/restart.log
```

### Check wallbox connection
```bash
curl -s http://localhost:5000/api/charge_points | python3 -m json.tool
```

### Restart tester
```bash
pkill -9 -f python && sleep 2
cd /home/ocpp-tester
nohup ./venv/bin/python3 ocpp-tester.py >> /tmp/restart.log 2>&1 &
sleep 5
curl http://localhost:5000/api/version
```

---

## Notes for Claude Code

- Always verify version after restarting
- Log version in test execution
- Update changelog when bumping version
- Kill Python before testing code changes
- Use version API to confirm correct code is running

---

Last updated: 2025-11-13
Current version: 1.1.0
