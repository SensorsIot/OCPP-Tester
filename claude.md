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

Last updated: 2025-11-13
Current version: 1.1.1

## Notes for Claude Code

- Always verify version after restarting
- Update changelog when bumping version
- Kill Python before testing code changes
- Use version API to confirm correct code is running
- All functional documentation goes in WallboxTester-FSD.md, not in this file
